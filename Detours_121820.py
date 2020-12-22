#################################################  DESCRIPTION  ########################################################
# Name: detours.py
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

import arcpy, datetime, os, sys

# Check out the Network Analyst extension license
arcpy.CheckOutExtension("Network")

# Set start time for code
print("Starting Workflow at time: {0}".format(datetime.datetime.now().strftime("%H:%M:%S")))

########################################### MODEL INPUTS & SETTINGS ####################################################

# Set Working Directory where input is stored and output will be stored
wd = r"F:\ITRE\Ag_Bridges\TraverseTests"


# Get input GDB from user
inputGDB = sys.argv[1]
# Output GDB Extension (appended to input name)
outExt = "_Det"

# Set variable names for data in input GDB
inNetworkDataset = r"Network/Network_ND"
destinations = r"Destinations"
businesses = r"businesses"
bridges = r"Weight_Restricted_Bridges"

brdgNoField = "BRDG_NBR"
snappables = ["Network_LocalStreets"]

########################################################################################################################

# Create GDB Copy
print("Creating GDB Copy for Output")
start = datetime.datetime.now()
gdbCopy = os.path.splitext(os.path.basename(inputGDB))[0] + outExt + ".gdb"
arcpy.Copy_management(inputGDB, wd + '\\' + gdbCopy)
print("\tFinished after {0}".format(str(datetime.datetime.now()-start)))

# Set Workspace to GDB Copy
arcpy.env.workspace = wd + '\\' + gdbCopy
arcpy.env.overwriteOutput = True

# Count number of detours to process
setList = arcpy.ListFeatureClasses("Bridges_by_Bus_*")
totalRows = 0
for s in setList:
    count = int(arcpy.GetCount_management(arcpy.env.workspace + "//" + s).getOutput(0))
    totalRows += count
print("Total Rows to Process: {0}".format(totalRows))

# Iterate through list of bridge tables
dests = arcpy.ListFeatureClasses(feature_dataset=destinations)
print(dests)

# Set iterating variables
x=0
startRow = datetime.datetime.now()

# Loop through bridge tables and calculate detours for each bridge-business pair
for dest in dests:
    print("Initiating Workflow for Destination: {0}\tat {1}".format(dest, datetime.datetime.now().strftime("%H:%M:%S")))
    # Set up Closest Facility Tool
    outNALayerName = dest + "_" + "CF"
    impedanceAttribute = "Length"
    inFacilities = destinations + "/" + dest

    # Copy bridge table from traversal step and setup new detour time field
    bridgeTable = arcpy.env.workspace + '\\' + "Bridges_by_Bus_{0}".format(dest)
    arcpy.Copy_management(bridgeTable, arcpy.env.workspace + '\\' + "detours_{0}".format(dest))
    detours = "detours_{0}".format(dest)
    newField = "No_Bridge_Time"
    arcpy.AddField_management(detours, newField, "DOUBLE")

    # Populate dictionary with bridges and the businesses that traverse them (used to determine bridge to remove)
    busDict = {}
    with arcpy.da.SearchCursor(detours, ["Business_ID", brdgNoField]) as sc:
        for row in sc:
            if row[0] not in busDict:
                busDict[row[0]] = [row[1]]
            else:
                busDict[row[0]].append(row[1])

    # Through businesses in dictionary, creating a feature layer for each to as facility
    for detourBusID in busDict:
        for removeBridgeNum in busDict[detourBusID]:
            # Create Feature Layer for each business
            arcpy.MakeFeatureLayer_management(businesses, "businessDetour", "OBJECTID = {0}".format(int(detourBusID)))
            inIncidents = "businessDetour"

            # Create Feature Layer for each bridge
            arcpy.MakeFeatureLayer_management(bridges, "removeBridge",
                                             "BRDG_NBR = '{0}'".format(removeBridgeNum))

            # Define barriers in Closest Facility as bridge
            barrier = "removeBridge"

            # Create a new closest facility analysis layer.
            outNALayer = arcpy.na.MakeClosestFacilityLayer(inNetworkDataset, outNALayerName, impedanceAttribute)

            # Get the layer object from the result object. The closest facility layer can
            # now be referenced using the layer object.
            outNALayer = outNALayer.getOutput(0)

            # Get the names of all the sublayers within the closest facility layer.
            subLayerNames = arcpy.na.GetNAClassNames(outNALayer)
            # Stores the layer names that we will use later
            facilitiesLayerName = subLayerNames["Facilities"]
            incidentsLayerName = subLayerNames["Incidents"]

            # Set valid snapping features from all features in network dataset
            descNet = arcpy.Describe(inNetworkDataset)
            sourceNames = [[i.name] for i in descNet.sources]
            for i in sourceNames:
                if i[0] in snappables:
                    i.append("SHAPE")
                else:
                    i.append("NONE")
            print("Source Names:", sourceNames)

            # Load Locations for Facilities, Incidents, and Barriers
            arcpy.na.AddLocations(outNALayer, facilitiesLayerName, inFacilities)
            arcpy.na.AddLocations(outNALayer, incidentsLayerName, inIncidents, '#', '#', '#', sourceNames)
            arcpy.na.AddLocations(outNALayer, "Point Barriers", barrier, '#', '#', '#', '#', '#', '#', "SNAP")

            # Solve the Closest Facility layer
            arcpy.na.Solve(outNALayer, "#", "CONTINUE")

            # Get detour time from route results; set detour time to None if not found
            try:
                z = max([int(i[15:]) for i in arcpy.ListDatasets("ClosestFacility*", "Feature")])
                routes = arcpy.env.workspace + "/" + "ClosestFacility{0}/CFRoutes{0}".format(z)
                routeRow = []
                with arcpy.da.SearchCursor(routes, ["IncidentID", "Total_Length", "SHAPE@"]) as sc2:
                    try:
                        routeRow = sc2.next()
                    except StopIteration:
                        routeRow = [detourBusID, None, None]
                key = "{0},{1}".format(detourBusID,removeBridgeNum)
            except:
                routeRow = [detourBusID, None, None]

            # Add detour time to detour table
            with arcpy.da.UpdateCursor(detours, ["Business_ID", brdgNoField, "No_Bridge_Time", "SHAPE@"]) as uc:
                for detoursRow in uc:
                    detKey = "{0},{1}".format(detoursRow[0],detoursRow[1])
                    if detKey == key:
                        detoursRow[2] = routeRow[1]
                        detoursRow[3] = routeRow[2]
                        uc.updateRow(detoursRow)

            # Get number for name of most recent Closest Facility Solution and delete it
            arcpy.Delete_management("ClosestFacility{0}".format(z))
            x+=1
            totalRows-=1
            endRow = datetime.datetime.now()

            # Print time statistics
            avgTime = (endRow-startRow)/x
            print("\tCompleted:\t{0}\n\tAvg. Time per Row:{1}\n\tRemaining Rows:{2}".format(x,avgTime,totalRows))
            print(datetime.datetime.now())

    # Calculate detour metrics in detours table
    detTime = "DET_TIME"
    arcpy.AddField_management(detours, detTime, "DOUBLE")
    subtractExp = "!No_Bridge_Time!-!Base_Length!"
    arcpy.CalculateField_management(detours, detTime, subtractExp, "PYTHON3")

    jobDetTime = "JOB_DET_TIME"
    arcpy.AddField_management(detours, jobDetTime, "DOUBLE")
    multExp = "!DET_TIME!*!Truck_Int!"
    arcpy.CalculateField_management(detours, jobDetTime, multExp, "PYTHON3")

    distWghtDetTime = "DISTW_JOB_DET_TIME"
    arcpy.AddField_management(detours, distWghtDetTime, "DOUBLE")
    multExp = "!DET_TIME!*!Truck_Int_DW!"
    arcpy.CalculateField_management(detours, distWghtDetTime, multExp, "PYTHON3")

# Merge all detour tables into single table
mergeDetours = arcpy.ListFeatureClasses("detours_*")
arcpy.Merge_management(mergeDetours, arcpy.env.workspace + '\\' + "Detours_Merged")

# Calculate summary of detour statistics by bridge and rename fields
arcpy.Frequency_analysis("Detours_Merged", "Detours_by_Bridge", brdgNoField, [detTime, jobDetTime, distWghtDetTime])
detSum = "DET_TIME_SUM"
arcpy.AlterField_management("Detours_by_Bridge", detTime, detSum, detSum)
jobDetSum = "JOB_DET_TIME_SUM"
arcpy.AlterField_management("Detours_by_Bridge", jobDetTime, jobDetSum, jobDetSum)
distWDetTimeSum = "DISTW_JOB_DET_TIME_SUM"
arcpy.AlterField_management("Detours_by_Bridge", distWghtDetTime, distWDetTimeSum, distWDetTimeSum)

# Join bridge metrics from detour table to bridges
arcpy.JoinField_management(bridges, brdgNoField, "Detours_by_Bridge", brdgNoField, [detSum, jobDetSum, distWDetTimeSum])

# Calc and print end time.
endingTime = datetime.datetime.now()
print(endingTime)
