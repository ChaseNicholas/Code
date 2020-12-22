#################################################  DESCRIPTION  ########################################################
# Name: traversals.py
#
# Description:  Uses the Closest Facility and Copy Traversed Source Features (Network Analyst) tools to produce the
#               following information:
#                 - The time (in minutes) from each business to the closest Destination for each cardinal direction.
#                 - The number of businesses and "trucking jobs" traversing each network segment and Bridge for each
#                   cardinal direction.
#                 - The specific bridges crossed by each Business for each cardinal direction.
#
# Inputs: Requires a File GDB containing, at a minimum the following data:
#                 - Pre-built Network
#                 - Feature class containing a "flat" polyline version of the road network
#                 - Feature dataset containing feature classes for point destinations on major (non-weight-restricted)
#                   network segments at the state border
#                 - Feature class containing point locations for Businesses
#                 - Feature class containing point locations for Weight Restricted Bridges
#
# Outputs:
#
# Requirements: Network Analyst Extension
#
# Estimated Run Time: 6-12 hours
########################################################################################################################

# Import system modules and  set up workspace
import time
import datetime, sys
import arcpy, os
# Check out the Network Analyst extension license
arcpy.CheckOutExtension("Network")

# Set start time for code (used to test run time)
startingTime = datetime.datetime.now()
print("Starting Workflow at time: {0}".format(datetime.datetime.now().strftime("%H:%M:%S")))

########################################### MODEL INPUTS & SETTINGS ####################################################

# Set Working Directory where input is stored and output will be stored
wd = r"F:\ITRE\Ag_Bridges\TraverseTests"

# Get input GDB from user
inputGDB = sys.argv[1]
# Output GDB Extension (appended to input name)
outExt = "_Trav"

# Set variable names for data in input GDB
inNetworkDataset = r"Network/Network_ND"
flatNetwork = r"Network_Recombined"
destinations = r"Destinations"
businesses = r"businesses"
bridges = r"Weight_Restricted_Bridges"

# Define trucking intensity field name in business data
truckIntRaw = "Truck_Int_Raw"

# Define bridge identifier field (bridge number) in bridge data
bridgeIDField = "BRDG_NBR"

# Define permitted features for initial street access from businesses (exclude limited access routes)
snappables = ["Network_LocalStreets"]

# Set variable names for XY Field names in business and bridges data (must be same GCS) (used for distance calc)
ogBusXField = 'POINT_X'
ogBusYField = 'POINT_Y'
ogBridgeXField = 'X_COORD'
ogBridgeYField = 'Y_COORD'

# Select whether or not to calculate traversals for network segments (greatly increases run time)
calcNetwork = "False"
# Set variables for business to bridge distance weighting (default cutoff = 1, default power = 1)
cutoff = '1'
power = '1'

########################################################################################################################

# Create GDB Copy in working directory
print("Creating GDB Copy for Output")
start = datetime.datetime.now()
gdbCopy = os.path.splitext(os.path.basename(inputGDB))[0] + outExt + ".gdb"
arcpy.Copy_management(inputGDB, wd + '\\' + gdbCopy)
print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))

# Set Workspace to GDB Copy
arcpy.env.workspace = wd + '\\' + gdbCopy
print(arcpy.env.workspace)
arcpy.env.overwriteOutput = True

# Get list of border point feature classes
dests = arcpy.ListFeatureClasses(feature_dataset=destinations)
print("Destinations: {0}".format(dests))
n = 1

# Calculate new trucking intensity by dividing raw TI by number of routes to be generated for each business
print("Dividing Trucking Intensity by Number of Destinations")
truckIntDiv = len(dests)
arcpy.AddField_management(businesses, "Truck_Int", "FLOAT")
truckInt = "Truck_Int"
arcpy.CalculateField_management(businesses, truckInt, '!Truck_Int_Raw!/{0}'.format(truckIntDiv), "PYTHON3")

# Loop through Traversal workflow for each set of border points
for dest in dests:
    # Set local variables
    outNALayerName = dest + "_" + "CF"
    impedanceAttribute = "Length"
    inFacilities = destinations + "/" + dest
    inIncidents = businesses

    # Create a new closest facility analysis layer.
    print("Initiating Workflow for Destination: {0}\tat {1}".format(dest, datetime.datetime.now().strftime("%H:%M:%S")))
    print("\tStarting Workflow at time: {0}".format(datetime.datetime.now().strftime("%H:%M:%S")))
    outNALayer = arcpy.na.MakeClosestFacilityLayer(inNetworkDataset, outNALayerName, impedanceAttribute)

    # Get the layer object from the result object. The closest facility layer can now be referenced using the layer
    # object.
    outNALayer = outNALayer.getOutput(0)
    desc = arcpy.Describe(outNALayer)

    # Get the names of all the sublayers within the closest facility layer.
    subLayerNames = arcpy.na.GetNAClassNames(outNALayer)
    # Stores the layer names that we will use later
    facilitiesLayerName = subLayerNames["Facilities"]
    incidentsLayerName = subLayerNames["Incidents"]

, thou    descNet = arcpy.Describe(inNetworkDataset)
    sourceNames = [[i.name] for i in descNet.sources]
    for i in sourceNames:
        if i[0] in snappables:
            i.append("SHAPE")
        else:
            i.append("NONE")
    print("Source Names:", sourceNames)

    # Load border point features as facilities and ensure that they are not located on restricted portions of the
    # network. Use default field mappings and search tolerance
    arcpy.na.AddLocations(outNALayer, facilitiesLayerName, inFacilities)
    arcpy.na.AddLocations(outNALayer, incidentsLayerName, inIncidents, '#', '#', '#', sourceNames)

    # Print descriptive locator information to confirm correct settings
    locCount = desc.locatorCount
    locators = desc.locators
    print("Total Locators: ", locCount)
    for i in range(0, locCount):
        sourceName = getattr(locators, "source" + str(i))
        snapType = getattr(locators, "snapType" + str(i))
        print("{0} : {1} : {2}".format(i, sourceName, snapType))

    # Solve the closest facility layer and copy the traversed source features to a temporary in-memory workspace. Use
    # default names for the output feature classes and table. Get only the first output which are the edges traversed.
    print("\tSolving Closest Facility and Traversed Edges")
    start = datetime.datetime.now()
    destEdges = dest + "_" + "TravEdges"
    delTravJunc = dest + "_" + "TravJunc"
    delTravTurn = dest + "_" + "TravTurn"

    # Print status of Hierarchy use to confirm correct setting
    print("Hierarchy:" + desc.useHierarchy)

    # Solve and copy traversed source features
    arcpy.CopyTraversedSourceFeatures_na(outNALayer, arcpy.env.workspace, destEdges,
                                         dest + "_" + "TravJunc", dest + "_" + "TravTurn")
    print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Spatially Join bridges to route features using one-to-many join
    print("\tJoining Bridge Traversals to Routes")
    start = datetime.datetime.now()
    routes = "ClosestFacility{0}/CFRoutes{0}".format(n)
    routesBridgesSJ = "routesBridgesSJ_" + dest
    arcpy.SpatialJoin_analysis(routes, bridges, routesBridgesSJ, "JOIN_ONE_TO_MANY", "#", "#",
                               "INTERSECT", "5 Feet")
    print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Create Bridge Table and set up to store unique business-bridge combinations with all necessary fields
    print("\tCreating Bridge Feature Class")
    start = datetime.datetime.now()
    arcpy.CreateFeatureclass_management(arcpy.env.workspace, "Bridges_by_Bus_{0}".format(dest), "POLYLINE", '#', '#',
                                        '#', arcpy.Describe(dest).spatialReference)
    bridgeTable = arcpy.env.workspace + r'/' + "Bridges_by_Bus_{0}".format(dest)
    busIDField = "Business_ID"
    arcpy.AddField_management(bridgeTable, busIDField, "LONG")
    arcpy.AddField_management(bridgeTable, bridgeIDField, "TEXT")
    arcpy.AddField_management(bridgeTable, "Base_Length", "DOUBLE")
    bridgeX = "Bridge_X"
    arcpy.AddField_management(bridgeTable, bridgeX, "DOUBLE")
    bridgeY = "Bridge_Y"
    arcpy.AddField_management(bridgeTable, bridgeY, "DOUBLE")

    # Write routes with non-null bridge crossings to Bridge Table using cursors
    try:
        sc = arcpy.da.SearchCursor(routesBridgesSJ, ["IncidentID", bridgeIDField, ogBridgeXField, ogBridgeYField,
                                                     "Total_Length", 'SHAPE@'], "BRDG_NBR IS NOT NULL")
        for row in sc:
            try:
                ic = arcpy.da.InsertCursor(bridgeTable, [busIDField, bridgeIDField, bridgeX, bridgeY,
                                                         "Base_Length", 'SHAPE@'])
                ic.insertRow(row)
                del ic
            except:
                print("ic failure")
        del sc
    except:
        print("sc failure")

    # Add coordinates of businesses and trucking intensity to bridge table using field join
    arcpy.JoinField_management(bridgeTable, busIDField, businesses, "OBJECTID", [ogBusXField, ogBusYField, truckInt])
    busX = "Business_X"
    arcpy.AlterField_management(bridgeTable, ogBusXField, busX, busX)
    busY = "Business_Y"income
    arcpy.AlterField_management(bridgeTable, ogBusYField, busY, busY)
    print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Calculate straight line distance from business to bridge in map units
    xyFeatureClass = "bus_to_bridge_dist_{0}".format(dest)
    arcpy.XYToLine_management(bridgeTable, xyFeatureClass, busX, busY, bridgeX, bridgeY, "GEODESIC")
    distMUField = "BUS_TO_BRIDGE_MU"
    arcpy.AddField_management(xyFeatureClass, distMUField, "DOUBLE")
    arcpy.CalculateField_management(xyFeatureClass, distMUField, '!Shape_Length!', "PYTHON3")

    # Join straight line distance back to bridges by business table and convert to miles
    arcpy.JoinField_management(bridgeTable, "OBJECTID", xyFeatureClass, "OID", [distMUField])
    distMiField = "BUS_TO_BRIDGE_MI"
    arcpy.AddField_management(bridgeTable, distMiField, "DOUBLE")
    arcpy.CalculateField_management(bridgeTable, distMiField, '!{0}!/5280'.format(distMUField), "PYTHON3")

    # Calculate unique distance-weighted trucking intensity value for each business-bridge pair
    truckIntDW = "Truck_Int_DW"
    arcpy.AddField_management(bridgeTable, truckIntDW, "DOUBLE")
    arcpy.CalculateField_management(bridgeTable, truckIntDW, '(!Truck_Int!*{0})/(!BUS_TO_BRIDGE_MI!**({1}))'.format(cutoff, power), "PYTHON3")
    
    # Calculate network traversals, if dummy variable is set to True
    if calcNetwork == "True":
        # Join job counts from businesses to routes
        print("\tJoining Job Counts to Routes")
        start = datetime.datetime.now()
        routes = "ClosestFacility{0}/CFRoutes{0}".format(n)
        arcpy.JoinField_management(routes, "IncidentID", businesses, "OBJECTID", truckInt)
        print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

        # Join job counts from routes to traversed features
        print("\tJoining Job Counts to Traversed Edges")
        start = datetime.datetime.now()
        arcpy.JoinField_management(destEdges, "RouteID", routes, "ObjectID", truckInt)
        print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

        # Calculate Join Field in Traversed Edges
        print("\tCalculating Join Field in Traversed Edges")
        start = datetime.datetime.now()
        arcpy.AddField_management(destEdges, "Network_Sect_Concat", "TEXT")
        arcpy.CalculateField_management(destEdges, "Network_Sect_Concat", '!SourceName! + str(!SourceOID!)', "PYTHON3")
        print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

        # Calculate the frequency of SourceOID in the traversed edges
        print("\tGenerating Frequency Table")
        start = datetime.datetime.now()
        destFreq = dest + "_" + "edgeFreq"
        arcpy.analysis.Frequency(destEdges, destFreq, "Network_Sect_Concat", truckInt)
        print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

        # Rename Fields
        netBusFreqField = dest + "_" + "TRAV_BUS"
        print("\tRenaming Frequency Field")
        arcpy.AlterField_management(destFreq, "FREQUENCY", netBusFreqField, netBusFreqField)

        netJobFreqField = dest + "_" + "TRAV_JOB"
        print("\tRenaming Trucking Job Field")
        arcpy.AlterField_management(destFreq, truckInt, netJobFreqField, netJobFreqField)

    # Calculate frequencies for bridges
    print("Calculating Frequencies for Bridges")
    freqTable = "{0}_FreqTable".format(dest)
    arcpy.Frequency_analysis(bridgeTable, freqTable, bridgeIDField, [truckInt, truckIntDW])

    freqField = dest + "_" + "TRAV_BUS"
    arcpy.AlterField_management(freqTable, "FREQUENCY", freqField, freqField)

    jobFreqField = dest + "_" + "TRAV_JOB"
    arcpy.AlterField_management(freqTable, truckInt, jobFreqField, jobFreqField)

    jobDWFreqField = dest + "_" + "TRAV_JOB_DISTW"
    arcpy.AlterField_management(freqTable, truckIntDW, jobDWFreqField, jobDWFreqField)

    arcpy.JoinField_management(bridges, bridgeIDField, freqTable, bridgeIDField,
                               [freqField, jobFreqField, jobDWFreqField])
    print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Iterate n
    n += 1

# Replace nulls with zeroes
print("Replacing Bridge Traversal Null Values with Zeros")
start = datetime.datetime.now()
bridgeFList = arcpy.ListFields(bridges, "*_TRAV_*")
codeBlock = """
def zeroNulls(value):
    if value == None:
        return 0
    else:
        return value"""
for field in bridgeFList:
    expression = "zeroNulls(!{0}!)".format(field.name)
    arcpy.CalculateField_management(bridges, field.name, expression, "PYTHON", codeBlock)
print("Finished after {0}".format(str(datetime.datetime.now() - start)))

# Calculate sum fields for bridges (traversals, TI-weighted traversals, fully weighted traversals)
print("Calculating Sum Fields for Bridges")
start = datetime.datetime.now()
arcpy.AddField_management(bridges, "BUS_TRAV_SUM", "LONG")
fieldList = ["!{0}!".format(f.name) for f in arcpy.ListFields(bridges, "*_TRAV_BUS*")]
sumExp = "+".join(fieldList)
arcpy.CalculateField_management(bridges, "BUS_TRAV_SUM", sumExp, "PYTHON3")

arcpy.AddField_management(bridges, "JOB_TRAV_SUM", "DOUBLE")
fieldList = ["!{0}!".format(f.name) for f in arcpy.ListFields(bridges, "*_TRAV_JOB")]
sumExp = "+".join(fieldList)
arcpy.CalculateField_management(bridges, "JOB_TRAV_SUM", sumExp, "PYTHON3")
print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))
print("Joining Frequencies to Bridges")
start = datetime.datetime.now()

arcpy.AddField_management(bridges, "DISTW_JOB_TRAV_SUM", "DOUBLE")
fieldList = ["!{0}!".format(f.name) for f in arcpy.ListFields(bridges, "*_TRAV_JOB_DISTW")]
sumExp = "+".join(fieldList)
arcpy.CalculateField_management(bridges, "DISTW_JOB_TRAV_SUM", sumExp, "PYTHON3")
print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))

# Determine process end time and duration
endingTime = datetime.datetime.now()
print("Process Complete. Total Duration for {0} destinations: {1}".format(len(dests), str(endingTime - startingTime)))

# Calculate final network sums and metrics, if dummy variable is set to True.
if calcNetwork == "True":
    # Join to Network Table
    print("\tJoining Frequency to Network")
    start = datetime.datetime.now()
    for destClass in arcpy.ListTables("*_edgeFreq"):
        inTable = flatNetwork
        inField = "Network_Sect_Name"
        joinTable = destClass
        joinField = "Network_Sect_Concat"
        fields = [f.name for f in arcpy.ListFields(joinTable, "*TRAV*")]
        arcpy.JoinField_management(inTable, inField, joinTable, joinField, fields)
        print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Export to new feature class
    print("Exporting Network to New Feature Class")
    start = datetime.datetime.now()
    arcpy.FeatureClassToFeatureClass_conversion(flatNetwork, arcpy.env.workspace, "Network_Joined")
    print("\t\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Replace nulls with zeroes
    print("Replacing Network Null Values with Zeros")
    start = datetime.datetime.now()
    networkFList = arcpy.ListFields("Network_Joined", "*TRAV*")
    codeBlock = """def zeroNulls(value):
        if value == None:
            return 0
        else:
            return value"""
    for field in networkFList:
        expression = "zeroNulls(!{0}!)".format(field.name)
        arcpy.CalculateField_management("Network_Joined", field.name, expression, "PYTHON", codeBlock)
    print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))

    # Calculate Sum Fields for Network
    print("Calculating Sum Fields for Network")
    start = datetime.datetime.now()
    arcpy.AddField_management("Network_Joined", "BUS_TRAV_SUM", "LONG")
    fieldList = ["!{0}!".format(f.name) for f in arcpy.ListFields("Network_Joined", "*TRAV_BUS*")]
    sumExp = "+".join(fieldList)
    arcpy.CalculateField_management("Network_Joined", "BUS_TRAV_SUM", sumExp, "PYTHON3")

    arcpy.AddField_management("Network_Joined", "JOB_TRAV_SUM", "DOUBLE")
    fieldList = ["!{0}!".format(f.name) for f in arcpy.ListFields("Network_Joined", "*TRAV_JOB*")]
    sumExp = "+".join(fieldList)
    arcpy.CalculateField_management("Network_Joined", "JOB_TRAV_SUM", sumExp, "PYTHON3")
    print("\tFinished after {0}".format(str(datetime.datetime.now() - start)))
