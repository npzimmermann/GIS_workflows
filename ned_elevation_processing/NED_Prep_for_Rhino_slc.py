# Python tool for QGIS to format Eastern MO / St Louis elevation rasters for import into Rhino via ASCImport_mod, 
# 	as a mesh that city vector layers can be projected onto (epsg 102696 in this case)
# Requirements of ASCImport_mod: 
#		Raster has a NODATA value assigned
#		Raster has square cells with single dimension for x/y

from qgis.core import QgsProject
from qgis.core import QgsMessageLog
from qgis.PyQt.QtCore import *
from PyQt4.QtGui import *
from qgis.gui import QgsMessageBar
from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator
import processing
import ogr
import math
from datetime import datetime

# Dict for mapUnit codes
mapUnitDict = { 0:'meters',1:'feet',2:'degrees',3:'Unknown units',4:'decimal degrees',5:'degrees mins secs',6:'degrees decimal mins',7:'nautical miles'}

# Dict for QGIS datatype codes
dTypeDict = { 'Byte':0, 'Int16':1, 'UInt16':2, 'UInt32':3, 'Int32':4, 'Float32':5, 'Float64':6 }

# NAD_1983_StatePlane_Missouri_East_FIPS_2401_Feet - prj used by city for many lyrs
crs_stateplaneft = QgsCoordinateReferenceSystem(102696, QgsCoordinateReferenceSystem.EpsgCrsId)
# NAD83 UTM15N - utm zone projection for St Louis
crs_utm15n = QgsCoordinateReferenceSystem(26915, QgsCoordinateReferenceSystem.EpsgCrsId)
# unprojected nad83 gcs 
crs_nad83 = QgsCoordinateReferenceSystem(4269, QgsCoordinateReferenceSystem.EpsgCrsId)

# NOTE - 
# 	DEM should already been clipped to focus region and should have z-units in meters
# 	If the input file's coordinate system units are meters or decimal degrees, the current cellsize value will be (way) too small,
# 	since the cellsize entered will be the final resolution in FEET

def selectLayer():
	qfd = QFileDialog()
	title = 'Open File'
	path = QDir().homePath()
	f = QFileDialog.getOpenFileName(qfd, title, path)
	fileInfo = QFileInfo(f)
	baseName = fileInfo.baseName()
	rlayer = QgsRasterLayer(f, baseName)
	qgisrlayer = iface.addRasterLayer(f, baseName)
 	if not rlayer.isValid():
		print "Layer failed to load!"
	else:
 		QgsMessageLog.logMessage("Processing layer "+ baseName)
		processDem(rlayer, fileInfo)


def processDem(rlayer, rlayerInfo):
	demClip_path = rlayerInfo.path()+"/"
	demClip_name = rlayerInfo.baseName()
	
	## Additional stats 
	# provider = rlayer.dataProvider()
	# stats = provider.bandStatistics(1, QgsRasterBandStats.All, rlayer.extent(), 0)
	# elevMin = stats.minimumValue
	# elevMax = stats.maximumValue
	# minmax_formatstr = 'min: {:.5f}, max: {:.5f} '.format(elevMin, elevMax)
	
	# Cell size and units
	cellSizeXY = [ rlayer.rasterUnitsPerPixelX(), rlayer.rasterUnitsPerPixelY() ]
 	rlayer_XYunits = mapUnitDict[ rlayer.crs().mapUnits() ]
 	cellsize_formatstr = 'x: {:.5f}, y: {:.5f} '.format(cellSizeXY[0], cellSizeXY[1])

	print "Coordinate system: "+ rlayer.crs().authid() +" ("+rlayer_XYunits +")" #rlayer.crs().authid()
	print "Current cell size ("+rlayer_XYunits+")\n"+str(cellsize_formatstr)

	# Set cell size for raster output ################### 	
	qid_cell = QInputDialog()
	label = "Current cell size ("+rlayer_XYunits+")\n"+str(cellsize_formatstr)+"\n\nEnter single number for new square cells (in feet!):"

	# Output cell size defaults to 100f
	min_valid = 100
	# unless units are in feet, in which case default to larger of the current x/y dimensions (rounded up)
	if rlayer_XYunits == 'feet':
		min_valid = max(cellSizeXY)
	default = math.ceil(min_valid)
	
	cellsize_input, ok = QInputDialog.getText(qid_cell, "Enter Cell Size", label, QLineEdit.Normal, str(default))
	# Validate entry
	if is_number(cellsize_input) and cellsize_input >= max(cellSizeXY[0], cellSizeXY[1]):
		msg = "Cell size set to " + str(cellsize_input)
		iface.messageBar().pushMessage("Parameter Set", str(msg), level=QgsMessageBar.INFO, duration=3)
	else:
		err_msg = "Invalid cell size: Must be a number over " +str(max(cellSizeXY[0], cellSizeXY[1]))+ ". Reverting to default ("+str(default)+")"
		iface.messageBar().pushMessage("Error", err_msg, level=QgsMessageBar.WARNING, duration=5)
		cellsize_input = default
	# Set output cellsize param
	cellsize = cellsize_input

	# Options...uses datetime values for default output filename to be unique enough to avoid overwrite without being random / irrelevant
	date = datetime.today().date()
	time = datetime.now().time()
	default_filename = "output_"+cellsize+"f_"+str('{:%b}'.format(date))+str(date.day)+"_"+str(time.hour)+"."+str(time.minute) #+"."+str(time.second)
	qid_outfile = QInputDialog()
	label = "Enter name for output (no extension)\n(files saved to input directory)"
	default = default_filename
	savefile_input, ok = QInputDialog.getText(qid_outfile, "Save Output As", label, QLineEdit.Normal, default)
	validname = ok_filename(savefile_input)	
	# Validate entry
	if validname == savefile_input:
		msg = "Output file will be saved as: '"+ str(validname) +"'."
		iface.messageBar().pushMessage("Parameter Set", str(msg), level=QgsMessageBar.INFO, duration=3)
	else:
		err_msg = "Invalid characters, adjusted file name to '"+ str(validname) + "'."
		iface.messageBar().pushMessage("Error", err_msg, level=QgsMessageBar.WARNING, duration=5)
	# Set output name param
	output_tif = demClip_path + validname+".tif"
	output_asc = demClip_path + validname+".asc"
	print "New cellsize of "+validname+" will be "+str(cellsize)+"ft"

	input_crs_id = rlayer.crs().authid()
	output_rlayerbounds = processing.runalg('modelertools:rasterlayerbounds', demClip_name)
	output_warpreproject  = processing.runalg('gdalogr:warpreproject', demClip_name, input_crs_id,'EPSG:102696','0',cellsize,1,False,output_rlayerbounds['EXTENT'],input_crs_id,5,4,75.0,6.0,1.0,False,0,False,None,None)

	# Saves elevation values as integers to reduce filesize of large ASC grids.
	elev_type = dTypeDict['Int16']	
	# For more precision:  
	#elev_type = dTypeDict['Float32']
	output_rastercalc = processing.runalg('gdalogr:rastercalculator', output_warpreproject['OUTPUT'],'1',None,'1',None,'1',None,'1',None,'1',None,'1','(A*3.28084)','0',elev_type, None, output_tif)
	# Export ASC grid file to import into Rhino using ASCImport_mod plugin
	output_translate = processing.runalg('gdalogr:translate', output_rastercalc['OUTPUT'],100.0,True,'0',0,'',output_rlayerbounds['EXTENT'],False,5,4,75.0,6.0,1.0,False,0,False,None, output_asc)
	qgis_newrlayer = iface.addRasterLayer(output_tif, validname)
	return iface.messageBar().pushMessage("Info", "Process complete", level=QgsMessageBar.INFO, duration=3)

def is_number(s):
	try:
		float(s)
		return True
	except ValueError:
		pass
	return False

def ok_filename(s):
	ok_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
	ok_name = ''.join(c for c in s if c in ok_chars)
	ok_no_spaces = ok_name.replace(' ','_')
	return ok_no_spaces

# Launch
selectLayer()