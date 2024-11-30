# Generates an overall transit connection score for each block/feature in census_blocks
#   Connection score = count of all unique routes within a five minute walk from the center of each block

streets_name = '1HrWalkableRoads_NoHighways'
route_stops_name = 'trimet_route_stops'
routes_name = 'trimet_routes'
blocks_name = 'census_blocks_land_only'
#centroids_name = 'census_block_centroids_land_only'

street_layer = QgsProject.instance().mapLayersByName(streets_name)[0]
route_stops_layer = QgsProject.instance().mapLayersByName(route_stops_name)[0]
routes_layer = QgsProject.instance().mapLayersByName(routes_name)[0]
blocks_layer = QgsProject.instance().mapLayersByName(blocks_name)[0]
#centroids_layer = QgsProject.instance().mapLayersByName(centroids_name)[0]

walk_feet_per_hour = 14784  #feet walkable in one hour assuming a walking speed of 2.8 mph
walk_km_per_hour = 4.50616
ft_to_m = 3.28084
time_limit_hour = 5/60
buffer_distance = walk_feet_per_hour * time_limit_hour #feet walkable in 5 minutes = 1232


# Selects features from layer matching rt_num and rt_dir
def select_by_route(layer, rt_num, rt_dir):
    layer.removeSelection()
    exp_string = f' "rte" is {rt_num} and "dir" is {rt_dir}'
    return processing.run("qgis:selectbyexpression", {
        'INPUT': layer,
        'EXPRESSION': exp_string, 'METHOD': 0})['OUTPUT']

# Create buffer around layer's selected features
# Returns the vector layer containing the buffer
def create_buffer(layer, distance):
    layer_uri = layer.dataProvider().dataSourceUri()
    buffer = processing.run("native:buffer",
        {'INPUT':
            QgsProcessingFeatureSourceDefinition(
                layer_uri,
                selectedFeaturesOnly=True,
                featureLimit=-1, geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
        'DISTANCE':distance,
        'SEGMENTS':5,
        'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,
        'DISSOLVE':False,'OUTPUT':'memory:'})['OUTPUT']
    #QgsProject.instance().addMapLayer(buffer)
    return buffer


# Clips a layer to a buffer
def clip_layer(layer, overlay):

    clipped = processing.run("native:clip",
                            {'INPUT': layer, 'OVERLAY':overlay,
                            'OUTPUT': 'memory:'})['OUTPUT']
    #QgsProject.instance().addMapLayer(clipped)
    return clipped

#return blocks within 10 ft of a feature
def get_nearby_blocks(feature):
    blocks = processing.run("native:extractwithindistance", 
                   {'INPUT':blocks_layer,
                    'REFERENCE':feature,'DISTANCE':10,
                    'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
    return blocks

def select_nearby_blocks(feature):
    processing.run("native:selectwithindistance", 
                   {'INPUT':blocks_layer,
                   'REFERENCE':feature,
                   'DISTANCE':10,'METHOD':0})


#finds the time to reach each stop within a street network
#no longer using, going from stops - > blocks
def get_paths_to_stops(network, stops):
    # get the coordinates from block centroid
    point = centroids_layer.selectedFeatures()[0].geometry().asPoint()
    point_str = f"{point.x()},{point.y()} [{centroids_layer.crs().authid()}]"

    # Note: due to this algorithm calculating distances on these layers in feet,
    #   we have to multiply the km/hr by ft_to_meters to get the correct times
    reachable_stops = processing.run("native:shortestpathpointtolayer",
                                     {'INPUT':network,'STRATEGY': 1,
                                      'DIRECTION_FIELD':'','VALUE_FORWARD':'',
                                      'VALUE_BACKWARD':'','VALUE_BOTH':'',
                                      'DEFAULT_DIRECTION':2,'SPEED_FIELD':'',
                                      'DEFAULT_SPEED': ft_to_m * walk_km_per_hour,
                                      'TOLERANCE':0,'START_POINT':point_str,
                                      'END_POINTS':stops, 'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
    #QgsProject.instance().addMapLayer(reachable_stops)
    return reachable_stops


# Gets service area using streets from a point
# Returns the portion of the network reachable from a 5 minute walk
def get_service_area(network, point):
    point_xy = point.geometry().asPoint()
    point_str = f"{point_xy.x()},{point_xy.y()} [{route_stops_layer.crs().authid()}]"
    
    service_area = processing.run("native:serviceareafrompoint", 
        {'INPUT':network,'STRATEGY':1,
        'DIRECTION_FIELD':'','VALUE_FORWARD':'',
        'VALUE_BACKWARD':'','VALUE_BOTH':'',
        'DEFAULT_DIRECTION':2,'SPEED_FIELD':'',
        'DEFAULT_SPEED': ft_to_m * walk_km_per_hour,
        'TOLERANCE':0,'START_POINT':point_str,
        'TRAVEL_COST2':5/60,'INCLUDE_BOUNDS':False,
        'OUTPUT_LINES':'TEMPORARY_OUTPUT'})['OUTPUT_LINES']
        
    return service_area






#########################################################################
# Creating, calculating score/route count
#########################################################################

# Idea for scoring for each route
def score(route):
    return route['CONNECTIONS'] * route['TRIPS_PER_HOUR'] * route["AVG_KPH"]

# Idea for pulling the score associated with a route from a stop
def get_route_score(stop):
    select_by_route(routes_layer, stop['rte'], stop['dir'])
    if len(routes_layer.selectedFeatures()) > 0:
        if len(routes_layer.selectedFeatures()) == 1:
            route = routes_layer.selectedFeatures()[0]
        # Some routes are broken into segments. Take only best score among segments
        else:
            best = routes_layer.selectedFeatures()[0]
            for route in routes_layer.selectedFeatures():
                if score(route) > score(best):
                    best = route
            route = best


# Get the count of how many unique routes can be reached within time constraint
def generate_route_count(stops):
    if 'cost' not in stops.fields().names():
        print("Error in counting reachable routes - expected routes to stops with costs")
        return

    route_count = 0
    counted = []
    for stop in stops.getFeatures():
        if stop['cost'] and stop['cost'] <= time_limit_hour:
            if f"{stop['rte']}-{stop['dir_desc']}" not in counted:
                route_count += 1
                counted.append(f"{stop['rte']}-{stop['dir_desc']}")
    return route_count, ", ".join(counted)


def add_route_to_blocks(stop):
    route_str = f"{stop['rte']}-{stop['dir_desc']}"
    blocks_layer.startEditing()
    for block in blocks_layer.getSelectedFeatures():
        routes_str = block['NEARBY_ROUTES']
        if not routes_str or route_str not in routes_str:
            if not routes_str:
                block['NEARBY_ROUTES'] = route_str
            else:   
                block['NEARBY_ROUTES'] = routes_str + (f", {route_str}")
            if not block['ROUTES_COUNT']:
                block['ROUTES_COUNT'] = 1
            else:
                block['ROUTES_COUNT'] = block['ROUTES_COUNT'] + 1
            blocks_layer.updateFeature(block)
    blocks_layer.commitChanges()


def add_transit_scores():
    for stop in route_stops_layer.getFeatures():
        # Buffer around route stops - radius = five minute walk (birds-eye distance)
        route_stops_layer.removeSelection()
        route_stops_layer.select(stop['fid'])
        buffer = create_buffer(route_stops_layer, buffer_distance)
        #QgsProject.instance().addMapLayer(buffer)

        # Clip blocks to what's within the buffer
        #clipped_blocks = clip_layer(blocks_layer, buffer)
        #QgsProject.instance().addMapLayer(clipped_blocks)

        # Clip street network to what's within the buffer
        clipped_streets = clip_layer(street_layer, buffer)
        #QgsProject.instance().addMapLayer(clipped_streets)

        # Get the service area walking from the stop
        stop_service_area = get_service_area(clipped_streets, stop)
        #QgsProject.instance().addMapLayer(stop_service_area)

        # Get blocks accessible from service area
        select_nearby_blocks(stop_service_area)

        add_route_to_blocks(stop)

        blocks_layer.removeSelection() 
        
    route_stops_layer.removeSelection()
    blocks_layer.commitChanges()


if 'ROUTES_COUNT' not in next(blocks_layer.getFeatures()).fields().names():
    blocks_layer.startEditing()
    blocks_layer.addAttribute(QgsField('ROUTES_COUNT', QVariant.Int))
    blocks_layer.addAttribute(QgsField('NEARBY_ROUTES', QVariant.String))
    blocks_layer.updateFields()

add_transit_scores()

