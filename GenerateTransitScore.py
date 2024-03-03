# Generates an overall transit score for each block/feature in

route_stops_name = 'trimet_route_stops'
stops_name = 'trimet_stops'
routes_name = 'trimet_routes'

route_stops_layer = QgsProject.instance().mapLayersByName(route_stops_name)[0]
stops_layer = QgsProject.instance().mapLayersByName(stops_name)[0]
routes_layer = QgsProject.instance().mapLayersByName(routes_name)[0]