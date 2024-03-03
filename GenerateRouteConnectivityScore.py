# For each Trimet route - Creates attribute field "Connections"
# Which contains the number of unique routes that are within 300 feet of any of the route's stops


route_stops_name = 'trimet_route_stops'
stops_name = 'trimet_stops'
routes_name = 'trimet_routes'

route_stops_layer = QgsProject.instance().mapLayersByName(route_stops_name)[0]
stops_layer = QgsProject.instance().mapLayersByName(stops_name)[0]
routes_layer = QgsProject.instance().mapLayersByName(routes_name)[0]

# Selects features from layer matching rt_num and rt_dir
def select_by_route(layer, rt_num, rt_dir):
    layer.removeSelection()
    exp_string = f' "rte" is {rt_num} and "dir" is {rt_dir}'
    processing.run("qgis:selectbyexpression", {
        'INPUT': layer,
        'EXPRESSION': exp_string, 'METHOD': 0})

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


#clips a layer to a buffer
def clip_layer(layer, overlay):

    clipped = processing.run("native:clip",
                            {'INPUT': layer, 'OVERLAY':overlay,
                            'OUTPUT': 'memory:'})['OUTPUT']
    #QgsProject.instance().addMapLayer(clipped)
    return clipped


# Returns list of all unique {rte, dir} pairs in a feature
def get_connected_routes(layer, rte, dr):
    connected_routes = []
    for f in layer.getFeatures():
        if f['rte'] is not None and f['dir'] is not None:
            if not (f['rte'] == rte and f['dir'] == dr):
                if [f['rte'], f['dir']] not in connected_routes:
                    connected_routes.append([f['rte'], f['dir']])
    return connected_routes


def add_connections():
    for route in routes_layer.getFeatures():
        if route['rte'] is not None and route['dir'] is not None:
            rte = route['rte']
            dr = route['dir']

            # Select all route_stops points on route
            select_by_route(route_stops_layer, rte, dr)

            # Buffer 300 feet (Roughly 1 large city block) around all stops
            buffer_layer = create_buffer(route_stops_layer, 300)

            # Get all stops within area around route's stops
            clipped_layer = clip_layer(route_stops_layer, buffer_layer)

            # Get the number of unique connections near this route
            connected_routes = get_connected_routes(clipped_layer, rte, dr)

            # Set connections number
            route['CONNECTIONS'] = len(connected_routes)
            routes_layer.updateFeature(route)

            print(f"*** ROUTE {rte}-{dr} CONNECTS TO")
            for i in connected_routes:
                print(f"          {i[0]},{i[1]}")


    routes_layer.commitChanges()




if 'CONNECTIONS' not in next(routes_layer.getFeatures()).attributes():
    routes_layer.startEditing()
    routes_layer.addAttribute(QgsField('CONNECTIONS', QVariant.Int))
    routes_layer.updateFields()
add_connections()


