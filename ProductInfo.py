#!/usr/bin/env python
import json
import os
import subprocess
import sys
import time
import zipfile
import argparse
import random
import socket
from collections import OrderedDict
import Common

kPcasLookupTable = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'product_info.json')
kTargetTableName    = 'Target2Pcas'
kPcasTableName      = 'pcasinfo'
kLegalObj           = 'legal'
kReleaseNotesUriObj = 'releasenotesuri'

def GetJsonObjects(aJsonFile):
    f = open(aJsonFile, 'rt')
    data = f.read()
    f.close()
    return json.loads(data)  # performs validation as well

def GetPcas( aProductName ):
    pcas = ""
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    pcasList = jsonObjs[kTargetTableName][aProductName]
    for entry in pcasList:
        pcas = entry
        break # not sure if/how to handle multiple entries
    return pcas

def GetNewVariant( aOldVariant ):
    old = aOldVariant
    prefix = ""
    if old.startswith( Common.kProductSuppressedString ):
        old = old.split('_')[1]
        prefix = Common.kProductSuppressedString + '_'

    if not old.startswith('Fw'):
        releaseVariantNew = "%sFw%s" % ( prefix, GetPcas( old ) )
    else:
        releaseVariantNew = aOldVariant
    return releaseVariantNew

def GetTarget( aPcas ):
    name = ""
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    pcasTable = jsonObjs[kTargetTableName]
    for target, pcasList in pcasTable.iteritems():
        for entry in pcasList:
            if pcasNum == entry:
                name = target
                break # not sure if/how to handle multiple entries
    return name

def GetLegal():
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kLegalObj]

def GetReleaseNotesUri():
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseNotesUriObj]

def GetPlatform( aPcas ):
    try:
        p,d = GetPlatformAndDescription( aPcas )
        return p
    except:
        return None

def GetDescription( aPcas ):
    try:
        p,d = GetPlatformAndDescription( aPcas )
        return d
    except:
        return None

def GetPlatformAndDescription( aPcas ):
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kPcasTableName].has_key( pcasNum ):
        pcasInfo = jsonObjs[kPcasTableName]
        return pcasInfo[pcasNum]["platform"], pcasInfo[pcasNum]["description"]
    else:
        for pcasinfo in jsonObjs[kPcasTableName].itervalues():
            if pcasinfo.has_key( "variants" ):
                for pcas, variantInfo in pcasinfo["variants"].iteritems():
                    if pcas == pcasNum:
                        return pcasinfo["platform"], variantInfo
    print "WARNING: could night find platform/description for: " + pcasStr
    raise ValueError("PcasNotFoundInInfoTable")

def GetTargets( aPlatform, aType='pcas', aIncRenew=False ):
    # aPlatform = 'core1' or 'core4'
    # aType = 'target', 'pcas', 'fw'
    devList = []
    prefix = "Fw" if aType == 'fw' else ""
    jsonObjs = GetJsonObjects( kPcasLookupTable )
    for pcas, pcasinfo in jsonObjs[kPcasTableName].iteritems():
        if pcasinfo["platform"] == aPlatform:
            if aType == 'target':
                devList.append( pcasinfo["legacytarget"] )
            else:
                devList.append( prefix + pcas )
                if pcasinfo.has_key( "variants" ):
                    varList = pcasinfo["variants"]
                    for var, varinfo in varList.iteritems():
                        if var != "826": # don't include renew devices
                            devList.append( prefix + var )
                            if "826" in varList and aIncRenew:
                                devList.append( prefix + "826_" + pcas )
                        elif aIncRenew:
                            devList.append( prefix + "826_" + pcas )
    #print "%s targets (%d): %s" % ( aPlatform, len(devList), devList )
    return devList

def DeviceTypeCount( aPlatform, aDevList ):
    count = 0
    if len(aDevList) > 0:
        # determine list type by first entry
        listType = GetTargetType( aDevList[0] )
        targets = GetTargets( aPlatform, listType )
        for dev in aDevList:
            if str(dev) in targets:
                count += 1
    return count

def GetTargetType( aTarget ):
    listType = 'target'
    if isinstance( aTarget, int ) or aTarget.isdigit(): 
        listType = 'pcas'
    elif 'fw' in aTarget.lower():
        listType = 'fw'
    return listType


def GetAllTargets():
    # returns a full integer list of pcas targets available, sorted by pcas number
    core1 = GetTargets( "core1" )
    core4 = GetTargets( "core4" )
    allDevs = core1 + core4
    return sorted(allDevs, key=int)

def GetCore1Targets():
    # returns a full integer list of pcas targets available, sorted by pcas number
    core1 = GetTargets( "core1" )
    return sorted(core1, key=int)

def GetCore4Targets():
    # returns a full integer list of pcas targets available, sorted by pcas number
    core4 = GetTargets( "core4" )
    return sorted(core4, key=int)


def Core1Count( aDevList ):
    return DeviceTypeCount( 'core1', aDevList )

def Core4Count( aDevList ):
    return DeviceTypeCount( 'core4', aDevList )

def IncludesAllCore1Devices( aDevList ):
    devCount = Core1Count( aDevList )
    core1 = GetCore1Targets()
    return devCount == len(core1)

def IncludesAllCore4Devices( aDevList ):
    devCount = Core4Count( aDevList )
    core4 = GetCore4Targets()
    return devCount == len(core4)

def GenerateSuppressioStringForJenkins():
    kJenkinsSuppressionParam = "____EnableSuppression____"
    core1list = []
    core4list = []
    alllist =   []
    
    for pcas in GetCore1Targets():
        core1list.append( "\"%s (Pcas %s: %s):selected\"" % (GetTarget(pcas), str(pcas), GetDescription(pcas).replace(",","-")) )

    for pcas in GetCore4Targets():
        core4list.append( "\"%s (Pcas %s: %s):selected\"" % (GetTarget(pcas), str(pcas), GetDescription(pcas).replace(",","-")) )

    for pcas in GetAllTargets():
        alllist.append( "\"%s (Pcas %s: %s):selected\"" % (GetTarget(pcas), str(pcas), GetDescription(pcas).replace(",","-")) )

    # lists are sorted by pcas, this will re-sort by target name instead
    core1  = ",".join(sorted(core1list, key=str))
    core4  = ",".join(sorted(core4list, key=str))
    alldev = ",".join(sorted(alllist, key=str))

    groovyScript = """
        if ({0}.equals(\"None\")) {{
            return []
        }} else if ({0}.equals(\"Core1\")) {{
            return [
                {1}
            ]
        }} else if ({0}.equals(\"Core4\")) {{
            return [
                {2}
            ]
        }} else if ({0}.equals(\"All\")) {{
            return [
                {3}
            ]
        }} else {{
            return [\"Unknown Product Group: \" + {0}]
        }}
    """.format( kJenkinsSuppressionParam, core1, core4, alldev  )

    return groovyScript