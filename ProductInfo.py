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
import time
import shutil

kDateTime         = time.strftime( '%d %b %Y %H:%M:%S', time.localtime() )
kPcasLookupTable  = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'product_info.json')
kPcasTableName    = 'PcasInfo'
# keys from PcasInfo
kDescKey = "description"
kVerKey = "lateststable"
kTargetKey = "legacytarget"
kNameKey = "name"
kPlatKey = "platform"
kRenewNameKey = "renewname"
kRenewUrlKey = "renewurl"
kUrlKey = "url"
kVolkano1Key = "volkano1"
kVolkano1SourcesKey = "v1sources"
kSourceMapRcaFirst = "rcafirst"
kVarsKey = "variants"
kPcasInfoKeys = [kDescKey, kVerKey, kTargetKey, kNameKey, kPlatKey, kRenewNameKey, kRenewUrlKey, kUrlKey, kVolkano1Key, kVolkano1SourcesKey, kSourceMapRcaFirst]

kTargetTableName  = 'Target2Pcas'
kLegalObj         = 'legal'
kReleaseNotesObj  = 'releasenotes'
kReleaseInfoV1Obj = 'releaseinfoV1'
kStableInfoObj    = 'stablereleases'
kLatestInfoObj    = 'latestreleases'

def GetPcas( aProductName ):
    pcas = ""
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    pcasList = GetPcasList( aProductName )
    for entry in pcasList:
        pcas = entry
        break # not sure if/how to handle multiple entries
    return pcas

def GetPcasList( aProductName ):
    pcas = ""
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    pcasList = []
    try:
         pcasList = jsonObjs[kTargetTableName][aProductName]
    except KeyError:
         pcasList = jsonObjs[kTargetTableName][aProductName.replace( "Mk1", "" )]
    return pcasList

def GetOutputNames( aTarget ):
    names = []
    try:
        jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
        for pcas in jsonObjs[kTargetTableName][aTarget]:
            names.append( 'Fw' + pcas )
    except:
        names = [aTarget]
    return names

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
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    pcasTable = jsonObjs[kTargetTableName]
    for target, pcasList in pcasTable.iteritems():
        for entry in pcasList:
            if pcasNum == entry:
                name = target
                break # not sure if/how to handle multiple entries
    return name

def GetLegal():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kLegalObj]

def GetReleaseNotes(aReleaseType='stable'):
    relType = None
    if 'dev' in aReleaseType.lower():
        relType = 'dev'
    elif 'beta' in aReleaseType.lower():
        relType = 'beta'
    else:
        relType = 'stable'
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseNotesObj][relType]

def GetReleaseNotesBeta():
    return GetReleaseNotes('beta')

def GetReleaseNotesDev():
    return GetReleaseNotes('dev')

def GetV1DownloadUrlBase():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["downloadurlbase"]

def GetV1DownloadBetaDir():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["downloadbetadir"]

def GetV1DownloadDevelopmentDir():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["downloaddevdir"]

def GetV1DownloadStableDir():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["downloadstabledir"]

def GetV1DownloadNightlyDir():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["downloadnightlydir"]

def GetV1MinKonfigVersion():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["minkonfigversion"]

def GetV1ExaktLinkVersion():
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return jsonObjs[kReleaseInfoV1Obj]["exaktlink"]

def GetLatestReleaseInfo(aPlatform, aReleaseType):
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kLatestInfoObj][aPlatform] != None:
        return jsonObjs[kLatestInfoObj][aPlatform][aReleaseType]
    else:
        return None

def GetStableReleaseVersions(aPlatform):
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    return list(jsonObjs[kStableInfoObj][aPlatform].keys())

def GetStableReleaseInfo(aVersion):
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kStableInfoObj]['core1'].has_key(aVersion):
        return jsonObjs[kStableInfoObj]['core1'][aVersion]
    elif jsonObjs[kStableInfoObj]['core4'].has_key(aVersion):
        return jsonObjs[kStableInfoObj]['core4'][aVersion]

    print "WARNING: could night find stable release info for: " + aVersion
    raise ValueError("MissingInfo")

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
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kPcasTableName].has_key( pcasNum ):
        pcasInfo = jsonObjs[kPcasTableName]
        return pcasInfo[pcasNum]["platform"], pcasInfo[pcasNum]["description"]
    else:
        for pcasinfo in jsonObjs[kPcasTableName].itervalues():
            if pcasinfo.has_key( "variants" ):
                for pcas, variantInfo in pcasinfo["variants"].iteritems():
                    if pcas == pcasNum:
                        return pcasinfo["platform"], variantInfo
    #print "WARNING: could night find platform/description for: " + pcasStr
    raise ValueError("MissingInfo")

def GetLatestStableRelease( aPcas ):
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kPcasTableName].has_key( pcasNum ):
        pcasInfo = jsonObjs[kPcasTableName]
        return pcasInfo[pcasNum]["lateststable"]
    else:
        for pcasinfo in jsonObjs[kPcasTableName].itervalues():
            if pcasinfo.has_key( "variants" ):
                for pcas, variantInfo in pcasinfo["variants"].iteritems():
                    if pcas == pcasNum:
                        return pcasinfo["lateststable"]
    print "WARNING: could night find latest stable release for: " + pcasStr
    raise ValueError("MissingInfo")

def GetTargets( aPlatform, aType='pcas', aIncRenew=False ):
    # aPlatform = 'core1' or 'core4'
    # aType = 'target', 'pcas', 'fw'
    devList = []
    prefix = "Fw" if aType == 'fw' else ""
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
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
                                devList.append( prefix + var + "_826" )
                        elif aIncRenew:
                            devList.append( prefix + pcas + "_826" )
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

def GetFirmwareVariant( aPcas ):
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    platform =  GetPlatform( pcasNum )
    if platform == "core1":
        fwVar = "Fw%s" % pcasNum
    elif platform == "core4":
        fwVar = "%s" % pcasNum
    else:
        raise ValueError("PcasInvalid")
    return fwVar

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

def GetCore1TargetsIncRenew():
    # returns a full integer list of pcas targets available, sorted by pcas number
    core1 = GetTargets( "core1", "pcas", True )
    core1.sort(key=lambda e: int(e.split('_')[0]))
    return core1

def HasRenew( aPcas ):
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    core1 = GetTargets( "core1", "pcas", True )
    return (pcasNum + "_826") in core1

def GetRenewName( aPcas ):
    pcasStr = str(aPcas)
    pcasNum = pcasStr.lower().replace("pcas", "").replace("fw", "")
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    if jsonObjs[kPcasTableName].has_key( pcasNum ):
        pcasInfo = jsonObjs[kPcasTableName]
        return pcasInfo[pcasNum]["renewname"]
    else:
        for pcasinfo in jsonObjs[kPcasTableName].itervalues():
            if pcasinfo.has_key( "variants" ):
                for pcas, variantInfo in pcasinfo["variants"].iteritems():
                    if pcas == pcasNum:
                        return pcasinfo["renewname"]

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

def GetLatestVersionsCore1( ):
    return GetLatestVersions( 'core1' )

def GetLatestVersionsCore4( ):
    return GetLatestVersions( 'core4' )

def GetLatestVersions( aPlatform ):
    beta = None
    stable = None

    rlsInfo = GetLatestReleaseInfo(aPlatform, 'stable')
    if rlsInfo != None:
        stable = rlsInfo["version"]
    else:
        Common.Info( '[FAIL]    No valid stable release version found for %s' % ( aPlatform ) )
        sys.exit(2)
    
    rlsInfo = GetLatestReleaseInfo(aPlatform, 'beta')
    if rlsInfo != None:
        # if beta is identical to stable, don't report it
        beta = rlsInfo["version"] if rlsInfo["version"] != stable else None
    else:
        Common.Info( '[WARNING]    No valid beta release version found for %s' % ( aPlatform ) )

    rlsList = GetStableReleaseVersions(aPlatform)

    print( "Latest device versions for %s: %s (beta), %s (stable)" % ( aPlatform, beta, stable ) )
    print( "Stable release version list for %s: %s" % ( aPlatform, rlsList ) )
    return { 'beta': beta, 'stable': stable, 'releaseList': rlsList }

def SuppressioStringForJenkins():
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

def CreateV1Feed(aFile, aVersion, aDownloadSubDir, aSuppressionList, aMinKonfigVersion=None, aExaktLink=None):
    def GetFeedSectionProducts():
        pcasListJson = []
        for item in GetCore1TargetsIncRenew():
            pcas = str(item)
            entry = {}
            if "_" in pcas:
                # handle renew variants differently
                pcasGroup = pcas.split("_")
                entry["pcas"] = pcasGroup
                pcas = pcasGroup[0]
            else: 
                entry["pcas"] = [pcas]
            entry["variantid"] = GetTarget(pcas)
            pcasListJson.append( entry )
        return pcasListJson

    def GetFeedSectionProductsV2():
        pcasListJson = []
        jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
        for pcas, pcasinfo in jsonObjs[kPcasTableName].iteritems():
            if pcasinfo["platform"] == "core1":
                entry = {}
                entry["variantid"] = pcasinfo["legacytarget"]
                pcasList = []
                pcasList.append(pcas)
                if pcasinfo.has_key( "variants" ):
                    varList = pcasinfo["variants"]
                    for var, varinfo in varList.iteritems():
                        if var != "826": # don't include renew devices
                            pcasList.append( var )
                entry["pcas"] = pcasList
                pcasListJson.append( entry )
        pcasListJson.sort(key=lambda e: int(e["pcas"][0]))
        return pcasListJson

    def GetFeedSectionLatestStable():
        rlsInfo = GetLatestReleaseInfo('core1', 'stable')
        section = GetFeedSectionReleases(rlsInfo['date'], rlsInfo['version'], GetV1DownloadStableDir(), rlsInfo['suppress'], rlsInfo['minkonfigversion'], rlsInfo['exaktlink'])
        return section

    def GetFeedSectionReleases(aDateTime, aVersion, aDownloadSubDir, aSuppressionList, aMinKonfigVersion=None, aExaktLink=None):
        quality = "release"
        uriHasVersionDir = False
        if 'beta' in aDownloadSubDir.lower() or 'dev' in aDownloadSubDir.lower():
            quality = "beta"
            uriHasVersionDir = True
        elif 'nightly' in aDownloadSubDir.lower():
            quality = "nightly"
            uriHasVersionDir = True

        relListJson = []
        for item in GetTargets( "core1" ):
            pcas = str(item)
            var = "Fw%s" % pcas
            legalInfo = GetLegal()
            minkonver = GetV1MinKonfigVersion() if aMinKonfigVersion is None else aMinKonfigVersion
            exaktlnk = GetV1ExaktLinkVersion() if aExaktLink is None else aExaktLink
            date = aDateTime
            version = aVersion

            if aSuppressionList != None and var in aSuppressionList:
                if quality == "release":
                    version = GetLatestStableRelease(item)
                    rlsInfo = GetStableReleaseInfo(version)
                    date = rlsInfo['date']
                    minkonver = rlsInfo['minkonfigversion']
                    exaktlnk = rlsInfo['exaktlink']
                else:
                    continue # skip suppressed entries for non-stable feed info

            rel = {
                "date": "%s" % date,
                "exaktlink": "%s" % exaktlnk,
                "licenseurl": "%s" % legalInfo["licenseurl"],
                "minkonfigversion": "%s" % minkonver,
                "privacyuri": "%s" % legalInfo["privacyuri"],
                "privacyurl": "%s" % legalInfo["privacyurl"],
                "privacyversion": legalInfo["privacyversion"],
                "quality": "%s" % quality,
                "releasenotesuri": "%s" % GetReleaseNotes(aDownloadSubDir),
                "uri": "{0}/{1}{2}/{3}_{4}.zip".format( GetV1DownloadUrlBase(), aDownloadSubDir, "/" + version if uriHasVersionDir else "", var, version ),
                "variantids": [
                    "%s" % var
                ],
                "version": "%s" % version
            }
            relListJson.append( rel )
        relListJson.sort(key=lambda e: int(e["variantids"][0].replace("Fw", "")))
        return relListJson

    feed = {}

    # pcas lookup table and release info
    feed["products"] = GetFeedSectionProducts()
    feed["productsV2"] = GetFeedSectionProductsV2()


    relListJson = []
    if 'dev' in aDownloadSubDir.lower() or 'beta' in aDownloadSubDir.lower():
        relListJson += GetFeedSectionLatestStable() # beta and dev carry latest stable as well for reverting back
    relListJson += GetFeedSectionReleases(kDateTime, aVersion, aDownloadSubDir, aSuppressionList) # info for this release
    feed["releases"] = relListJson

    Common.CreateJsonFile( feed, aFile )

def CreateV1DevelopmentFeed(aFile, aVersion, aSuppressionList):
    CreateV1Feed(aFile, aVersion, GetV1DownloadDevelopmentDir(), aSuppressionList)
    UpdateLatestReleaseInfoCore1('dev', aVersion, aSuppressionList)

def CreateV1BetaFeed(aFile, aVersion, aSuppressionList):
    CreateV1Feed(aFile, aVersion, GetV1DownloadBetaDir(), aSuppressionList)
    UpdateLatestReleaseInfoCore1('beta', aVersion, aSuppressionList)

def CreateV1NightlyFeed(aFile, aVersion):
    CreateV1Feed(aFile, aVersion, GetV1DownloadNightlyDir(), None)
    UpdateLatestReleaseInfoCore1('nightly', aVersion, None)

def CreateV1ReleaseFeed(aFile, aVersion, aIsPromotionFromDev, aUpdateReleaseInfo):
    rlsInfo = None
    if aIsPromotionFromDev:
        rlsInfo = GetLatestReleaseInfo('core1', 'dev')
    else:
        rlsInfo = GetLatestReleaseInfo('core1', 'beta')
    if rlsInfo == None or rlsInfo['version'] != aVersion:
        return False
    
    CreateV1Feed(aFile, aVersion, GetV1DownloadStableDir(), rlsInfo['suppress'], rlsInfo['minkonfigversion'], rlsInfo['exaktlink'])
    if aUpdateReleaseInfo:
        UpdateLatestReleaseInfoCore1('stable', aVersion, rlsInfo['suppress'], rlsInfo['minkonfigversion'], rlsInfo['exaktlink'])
    return True

def UpdateLatestReleaseInfoCore1(aReleaseType, aVersion, aSuppressionList, aMinKonfigVersion=None, aExaktLink=None):
    UpdateLatestReleaseInfo('core1', aReleaseType, aVersion, aSuppressionList, aMinKonfigVersion, aExaktLink)

def UpdateLatestReleaseInfoCore4(aReleaseType, aVersion, aSuppressionList):
    UpdateLatestReleaseInfo('core4', aReleaseType, aVersion, aSuppressionList)

def UpdateLatestReleaseInfo(aPlatform, aReleaseType, aVersion, aSuppressionList, aMinKonfigVersion=None, aExaktLink=None):
    relType = 'stable'
    if 'dev' in aReleaseType.lower():
        relType = 'dev'
    elif 'beta' in aReleaseType.lower():
        relType = 'beta'
    elif 'night' in aReleaseType.lower():
        relType = 'nightly'

    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    relObj = jsonObjs[kLatestInfoObj][aPlatform][relType]
    relObj['version'] = aVersion
    relObj['date'] = kDateTime
    relObj['suppress'] = aSuppressionList
    mk = GetV1MinKonfigVersion() if aMinKonfigVersion == None else aMinKonfigVersion
    relObj['minkonfigversion'] = mk
    el = GetV1ExaktLinkVersion() if aExaktLink == None else aExaktLink
    relObj['exaktlink'] = el

    if relType == 'stable':
        # set dev and beta to none on stable release
        jsonObjs[kLatestInfoObj][aPlatform]['dev'] = None
        jsonObjs[kLatestInfoObj][aPlatform]['beta'] = None
        # append this release to 'stablereleases'
        jsonObjs[kStableInfoObj][aPlatform][aVersion] = {'date': kDateTime, 'exaktlink': el, 'minkonfigversion': mk }
        # update 'lateststable' per pcas entry
        pcasOnlySuppressionList = [] if aSuppressionList == None else [s.replace("Fw", "") for s in aSuppressionList]
        for pcas, pcasinfo in jsonObjs[kPcasTableName].iteritems():
            if pcas not in pcasOnlySuppressionList:
                pcasinfo['lateststable'] = aVersion

    Common.CreateJsonFile( jsonObjs, kPcasLookupTable )

def CommitAndPushReleaseInfo( aVersion, aDryRun ):
    Common.CommitAndPushFiles( Common.kOhDevToolsRepo, [kPcasLookupTable], "Upated product info for release %s" % aVersion, aDryRun )
    # also publish to cloud location? FIX ME??

def CreateCppPcasInfo( aFilePath=None ):
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    kKeyFirmwareVariant = "fwvar"
    cpp = """#pragma once

#include <OpenHome/OhNetTypes.h>
#include <OpenHome/Private/Standard.h>
#include <map>
#include <string>

EXCEPTION(PcasNotFound);

using namespace OpenHome;

namespace Linn
{
namespace Target
{
    typedef std::map<std::string, std::string> PcasData;
    typedef std::map<TUint, PcasData> PcasDict;\n
"""
    cpp += "    static const TChar* kKeyPcasDescription = \"%s\";\n" % kDescKey
    cpp += "    static const TChar* kKeyPcasLatestStable = \"%s\";\n" % kVerKey
    cpp += "    static const TChar* kKeyPcasLegacyTarget = \"%s\";\n" % kTargetKey
    cpp += "    static const TChar* kKeyPcasName = \"%s\";\n" % kNameKey
    cpp += "    static const TChar* kKeyPcasPlatform = \"%s\";\n" % kPlatKey
    cpp += "    static const TChar* kKeyPcasRenewName = \"%s\";\n" % kRenewNameKey
    cpp += "    static const TChar* kKeyPcasRenewUrl = \"%s\";\n" % kRenewUrlKey
    cpp += "    static const TChar* kKeyPcasUrl = \"%s\";\n" % kUrlKey
    cpp += "    static const TChar* kKeyPcasVolkano1 = \"%s\";\n" % kVolkano1Key
    cpp += "    static const TChar* kKeyPcasVolkano1Sources = \"%s\";\n" % kVolkano1SourcesKey
    cpp += "    static const TChar* kKeyPcasSourceMapRcaFirst = \"%s\";\n" % kSourceMapRcaFirst
    cpp += "    static const TChar* kKeyPcasFirmwareVariant = \"%s\";\n" % kKeyFirmwareVariant

    cpp += """
    static const PcasDict kPcasDict = {
"""
    for pcas, pcasinfo in jsonObjs[kPcasTableName].iteritems():
        pcasNum = int(pcas)
        varList = [pcasNum]
        descList = {pcasNum:pcasinfo[kDescKey]}
        if kVarsKey in pcasinfo:
            for varpcas, vardesc in pcasinfo[kVarsKey].iteritems():
                varNum = int(varpcas)
                if varNum != 826:
                    varList.append( varNum )
                    descList[varNum] = vardesc
        for var in varList:
            cpp += "        { %d, {" % var
            for key in kPcasInfoKeys:
                if key in pcasinfo:
                    val = pcasinfo[key] if key != kDescKey else descList[var]
                    cpp += "{\"%s\", \"%s\"}, " % (key, val)
            cpp += "{\"%s\", \"%s\"}" % (kKeyFirmwareVariant, GetFirmwareVariant(var))
            cpp += "} },\n"
    
    cpp += """
    };

    class PcasInfo
    {
    public:
        static const TChar* GetModelName(TUint aPcas, TBool aIsRenew)
        {
            if (aIsRenew) {
                return Get(kKeyPcasRenewName, aPcas);
            }
            else {
                return Get(kKeyPcasName, aPcas);
            }
        }

        static const TChar* GetUrl(TUint aPcas, TBool aIsRenew)
        {
            if (aIsRenew) {
                return Get(kKeyPcasRenewUrl, aPcas);
            }
            else {
                return Get(kKeyPcasUrl, aPcas);
            }
        }

        static const TChar* GetDescription(TUint aPcas)
        {
            return Get(kKeyPcasDescription, aPcas);
        }

        static const TChar* GetLegacyVariantStr(TUint aPcas)
        {
            return Get(kKeyPcasLegacyTarget, aPcas);
        }

        static const TChar* GetFirmwareVariant(TUint aPcas)
        {
            return Get(kKeyPcasFirmwareVariant, aPcas);
        }

        static const TChar* GetLatestStableSoftwareVersion(TUint aPcas)
        {
            return Get(kKeyPcasLatestStable, aPcas);
        }

        static TBool IsCore1(TUint aPcas)
        {
            return  strcmp(Get(kKeyPcasPlatform, aPcas), "core1") == 0;
        }

        static TBool IsCore4(TUint aPcas)
        {
            return  strcmp(Get(kKeyPcasPlatform, aPcas), "core4") == 0;
        }

        static TBool IsVolkano1(TUint aPcas)
        {
            return  strcmp(Get(kKeyPcasVolkano1, aPcas), "True") == 0;
        }

        static TUint Volkano1Sources(TUint aPcas)
        {
            if (IsVolkano1(aPcas)) {
                return GetNum(kKeyPcasVolkano1Sources, aPcas);
            }
            else {
                return 0;
            }
        }

        static TBool SourceMapRcaFirst(TUint aPcas)
        {
            TBool rcaFirst = false;
            try {
                rcaFirst = strcmp(Get(kKeyPcasSourceMapRcaFirst, aPcas), "True") == 0;
            }
            catch (...) { }
            return rcaFirst;
        }

        static const TChar* Get(const TChar* aKey, TUint aPcas)
        {
            std::string key = aKey;
            for (auto& x: kPcasDict) {
                if (x.first == aPcas) {
                    return x.second.at(key).c_str();
                }
            }
            THROW(PcasNotFound);
        }

        static const TUint GetNum(const TChar* aKey, TUint aPcas)
        {
            return TUint(atoi(Get(aKey, aPcas)));
        }
    };
} // namespace Target
} // namespace Linn
"""

    if aFilePath != None:
        Common.CreateTextFile( cpp, os.path.join( aFilePath, "PcasInfo.h" ) )
    else:    
        print cpp
    return cpp

def TargetToPcasFileConversion( aFilePath ):
    # filter out renew files
    for f in os.listdir( aFilePath ):
        fullPath = os.path.join( aFilePath, f )
        if os.path.isfile( fullPath ):
            fname = f.lower()
            if "renew" in fname:
                if "akurate" in fname:
                    if "dsm" in fname:
                        adsmRenewFile = fullPath
                    elif "ds" in fname:
                        adsRenewFile = fullPath
                elif "klimax" in fname:
                    if "dsm" in fname:
                        kdsmRenewFile = fullPath
                    elif "ds" in fname:
                        kdsRenewFile = fullPath

    for f in os.listdir( aFilePath ):
        fullPath = os.path.join( aFilePath, f )
        if os.path.isfile( fullPath ):
            [name, ext] = os.path.basename( fullPath ).split('.')
            pcasList = []
            try:
                pcasList = GetPcasList( name )
            except:
                if "renew" not in f.lower():
                    print "SKIP %s" %  fullPath
                continue

            for entry in pcasList:
                newFile = os.path.join( aFilePath, GetFirmwareVariant( entry ) + "." + ext )
                print "COPY %s to %s" % ( fullPath, newFile )
                shutil.copy2( fullPath, newFile )
                if HasRenew( entry ):
                    newFile = os.path.join( aFilePath, GetFirmwareVariant( entry ) + "Renew." + ext )
                    renewName = GetRenewName( entry ).lower()
                    srcFile = None
                    if "akurate" in renewName:
                        if "dsm" in renewName:
                            srcFile = adsmRenewFile
                        elif "ds" in renewName:
                            srcFile = adsRenewFile
                    elif "klimax" in renewName:
                        if "dsm" in renewName:
                            srcFile = kdsmRenewFile
                        elif "ds" in renewName:
                            srcFile = kdsRenewFile
                    print "COPY %s to %s" % ( srcFile, newFile )
                    shutil.copy2( srcFile, newFile )
            os.remove( fullPath )
    
    # delete unused renew files
    os.remove( adsmRenewFile )
    os.remove( adsRenewFile )
    os.remove( kdsmRenewFile )
    os.remove( kdsRenewFile )

#print SuppressioStringForJenkins()
#CreateV1DevelopmentFeed("tempV1devFeed.json", "4.66.250", ["Fw913", "Fw1015"])
#CreateV1ReleaseFeed("tempV1stableFeed.json", "4.66.255", False)
#CreateV1NightlyFeed("tempV1nightlyFeed.json", "4.0.699")
#CreateV1BetaFeed("tempV1betaFeed.json", "4.66.259", ["Fw913", "Fw1015"])
#CommitAndPushReleaseInfo( "1.2.3", True )
#CreateCppPcasInfo(".")

#fp = "T:\\volkano2\\product\\Linn\\res\\icons"
#TargetToPcasFileConversion(fp)

# create ros.xml entries
#for f in os.listdir( fp ):
#    fullPath = os.path.join( fp, f )
#    if os.path.isfile( fullPath ):
#        print "  <entry    type=\"file\"   key=\"res/icons/{0}\">res/icons/{0}</entry>".format( f )

def UpdatePcasInfoFromDas():
    # get pcas numbers from products that are not main boards, add to PcasInfo if missing
    pl = [
    "PCAS670L2R2	4228	21.51%",
    "PCAS844L1R1	3760	19.13%",
    "PCAS670L2R1	2268	11.54%",
    "PCAS611L1R2	2162	11.00%",
    "PCAS915L1R2	1800	9.16%",
    "PCAS679L2R1	1612	8.20%",
    "PCAS670L1R1	1506	7.66%",
    "PCAS805L4R1	1435	7.30%",
    "PCAS770L1R3	1200	6.10%",
    "PCAS841L1R5	1000	5.09%",
    "PCAS950L1R2	957	4.87%",
    "PCAS953L1R3	918	4.67%",
    "PCAS802L4R2	908	4.62%",
    "PCAS841L2R1	878	4.47%",
    "PCAS862L2R5	857	4.36%",
    "PCAS876L2R2	753	3.83%",
    "PCAS723L6R2	752	3.83%",
    "PCAS610L1R2	669	3.40%",
    "PCAS802L4R1	647	3.29%",
    "PCAS799L3R1	630	3.20%",
    "PCAS954L1R1	582	2.96%",
    "PCAS799L2R6	576	2.93%",
    "PCAS841L1R4	566	2.88%",
    "PCAS840L2R2	523	2.66%",
    "PCAS903L1R4	510	2.59%",
    "PCAS840L1R3	500	2.54%",
    "PCAS805L2R1	496	2.52%",
    "PCAS875L4R2	470	2.39%",
    "PCAS989L1R2	446	2.27%",
    "PCAS765L1R6	439	2.23%",
    "PCAS863L2R2	437	2.22%",
    "PCAS679L1R1	427	2.17%",
    "PCAS875L6R1	388	1.97%",
    "PCAS716L2R3	386	1.96%",
    "PCAS901L2R1	381	1.94%",
    "PCAS901L1R4	325	1.65%",
    "PCAS840L1R1	301	1.53%",
    "PCAS765L1R5	296	1.51%",
    "PCAS716L2R2	296	1.51%",
    "PCAS826L2R2	292	1.49%",
    "PCAS842L1R1	288	1.46%",
    "PCAS903L1R3	288	1.46%",
    "PCAS822L1R1	284	1.44%",
    "PCAS797L1R7	280	1.42%",
    "PCAS723L3R3	278	1.41%",
    "PCAS716L2R4	278	1.41%",
    "PCAS793L3R2	274	1.39%",
    "PCAS840L2R1	270	1.37%",
    "PCAS698L1R1	269	1.37%",
    "PCAS838L1R5	266	1.35%",
    "PCAS749L2R3	262	1.33%",
    "PCAS697L2R2	247	1.26%",
    "PCAS960L2R3	245	1.25%",
    "PCAS961L1R4	239	1.22%",
    "PCAS841L1R6	238	1.21%",
    "PCAS803L2R3	233	1.19%",
    "PCAS802L2R1	224	1.14%",
    "PCAS716L5R1	216	1.10%",
    "PCAS837L1R5	210	1.07%",
    "PCAS697L1R2	210	1.07%",
    "PCAS826L1R1	203	1.03%",
    "PCAS986L1R3	200	1.02%",
    "PCAS862L2R7	199	1.01%",
    "PCAS915L1R1	198	1.01%",
    "PCAS716L2R9	190	0.97%",
    "PCAS992L1R1	186	0.95%",
    "PCAS953L1R2	185	0.94%",
    "PCAS1011L3R1	179	0.91%",
    "PCAS838L1R4	173	0.88%",
    "PCAS799L2R4	172	0.87%",
    "PCAS911L2R1	169	0.86%",
    "PCAS1008L1R2	164	0.83%",
    "PCAS911L2R2	159	0.81%",
    "PCAS961L1R3	159	0.81%",
    "PCAS837L2R5	158	0.80%",
    "PCAS960L2R2	156	0.79%",
    "PCAS765L1R8	155	0.79%",
    "PCAS950L1R1	154	0.78%",
    "PCAS988L1R1	153	0.78%",
    "PCAS793L4R1	151	0.77%",
    "PCAS826L4R1	150	0.76%",
    "PCAS876L2R1	148	0.75%",
    "PCAS697L2R3	141	0.72%",
    "PCAS858L6R1	139	0.71%",
    "PCAS799L2R7	136	0.69%",
    "PCAS723L2R2	131	0.67%",
    "PCAS974L3R1	130	0.66%",
    "PCAS678L2R2	127	0.65%",
    "PCAS1010L2R2	127	0.65%",
    "PCAS858L4R2	126	0.64%",
    "PCAS862L2R6	125	0.64%",
    "PCAS770L1R4	124	0.63%",
    "PCAS983L6R1	122	0.62%",
    "PCAS803L1R3	120	0.61%",
    "PCAS973L3R1	120	0.61%",
    "PCAS765L1R9	117	0.60%",
    "PCAS799L2R3	116	0.59%",
    "PCAS836L4R2	116	0.59%",
    "PCAS802L3R1	111	0.56%",
    "PCAS750L3R4	110	0.56%",
    "PCAS723L2R3	109	0.55%",
    "PCAS793L2R4	106	0.54%",
    "PCAS858L6R2	106	0.54%",
    "PCAS901L1R3	105	0.53%",
    "PCAS723L5R1	104	0.53%",
    "PCAS749L2R2	103	0.52%",
    "PCAS723L2R1	103	0.52%",
    "PCAS889L1R2	102	0.52%",
    "PCAS912L2R1	100	0.51%",
    "PCAS723L2R6	98	0.50%",
    "PCAS803L2R6	95	0.48%",
    "PCAS822L2R4	95	0.48%",
    "PCAS997L1R1	94	0.48%",
    "PCAS867L1R3	94	0.48%",
    "PCAS716L2R5	91	0.46%",
    "PCAS913L1R5	90	0.46%",
    "PCAS797L1R4	89	0.45%",
    "PCAS836L2R2	89	0.45%",
    "PCAS889L2R1	88	0.45%",
    "PCAS993L1R2	88	0.45%",
    "PCAS862L2R4	87	0.44%",
    "PCAS799L2R2	86	0.44%",
    "PCAS875L3R1	85	0.43%",
    "PCAS862L2R2	85	0.43%",
    "PCAS697L2R1	84	0.43%",
    "PCAS797L1R6	83	0.42%",
    "PCAS803L3R1	81	0.41%",
    "PCAS805L1R2	80	0.41%",
    "PCAS840L1R2	79	0.40%",
    "PCAS793L3R3	79	0.40%",
    "PCAS797L1R2	77	0.39%",
    "PCAS723L2R5	76	0.39%",
    "PCAS723L6R1	74	0.38%",
    "PCAS836L6R1	74	0.38%",
    "PCAS1010L2R1	74	0.38%",
    "PCAS803L2R2	72	0.37%",
    "PCAS867L1R7	72	0.37%",
    "PCAS901L1R2	72	0.37%",
    "PCAS889L1R8	69	0.35%",
    "PCAS716L2R11	66	0.34%",
    "PCAS765L1R7	65	0.33%",
    "PCAS987L2R1	63	0.32%",
    "PCAS678L2R3	62	0.32%",
    "PCAS793L2R3	62	0.32%",
    "PCAS862L2R3	62	0.32%",
    "PCAS836L1R3	60	0.31%",
    "PCAS770L1R2	59	0.30%",
    "PCAS750L1R1	58	0.30%",
    "PCAS805L3R1	58	0.30%",
    "PCAS911L1R4	58	0.30%",
    "PCAS841L1R3	58	0.30%",
    "PCAS723L6R3	56	0.28%",
    "PCAS716L2R1	56	0.28%",
    "PCAS750L3R1	55	0.28%",
    "PCAS889L1R4	55	0.28%",
    "PCAS797L1R1	54	0.27%",
    "PCAS750L3R5	53	0.27%",
    "PCAS792L1R6	52	0.26%",
    "PCAS750L3R2	51	0.26%",
    "PCAS765L1R4	50	0.25%",
    "PCAS973L2R3	50	0.25%",
    "PCAS678L2R5	47	0.24%",
    "PCAS749L1R2	47	0.24%",
    "PCAS803L2R4	45	0.23%",
    "PCAS792L1R2	45	0.23%",
    "PCAS810L1R6	45	0.23%",
    "PCAS998L1R1	44	0.22%",
    "PCAS716L4R1	44	0.22%",
    "PCAS723L1R3	43	0.22%",
    "PCAS876L1R1	42	0.21%",
    "PCAS836L2R1	42	0.21%",
    "PCAS716L4R2	42	0.21%",
    "PCAS836L3R2	41	0.21%",
    "PCAS889L1R9	40	0.20%",
    "PCAS911L1R3	40	0.20%",
    "PCAS912L1R3	39	0.20%",
    "PCAS889L1R3	39	0.20%",
    "PCAS1005L1R1	39	0.20%",
    "PCAS837L2R1	38	0.19%",
    "PCAS833L2R4	36	0.18%",
    "PCAS1008L2R1	36	0.18%",
    "PCAS833L2R1	35	0.18%",
    "PCAS810L1R3	35	0.18%",
    "PCAS716L2R6	35	0.18%",
    "PCAS750L3R8	34	0.17%",
    "PCAS678L1R1	34	0.17%",
    "PCAS799L2R5	34	0.17%",
    "PCAS797L1R3	33	0.17%",
    "PCAS797L1R5	33	0.17%",
    "PCAS858L3R2	33	0.17%",
    "PCAS903L1R2	32	0.16%",
    "PCAS837L2R4	31	0.16%",
    "PCAS912L1R4	31	0.16%",
    "PCAS867L1R8	31	0.16%",
    "PCAS867L1R5	31	0.16%",
    "PCAS750L3R9	30	0.15%",
    "PCAS863L2R1	29	0.15%",
    "PCAS723L3R5	29	0.15%",
    "PCAS822L2R1	29	0.15%",
    "PCAS914L2R1	28	0.14%",
    "PCAS850L2R5	27	0.14%",
    "PCAS973L2R4	26	0.13%",
    "PCAS862L2R1	26	0.13%",
    "PCAS826L2R1	25	0.13%",
    "PCAS723L3R4	24	0.12%",
    "PCAS913L1R3	23	0.12%",
    "PCAS678L2R4	23	0.12%",
    "PCAS716L2R10	22	0.11%",
    "PCAS803L2R5	22	0.11%",
    "PCAS838L1R3	22	0.11%",
    "PCAS792L1R3	22	0.11%",
    "PCAS1011L2R1	22	0.11%",
    "PCAS810L1R2	22	0.11%",
    "PCAS792L1R5	21	0.11%",
    "PCAS990L1R1	21	0.11%",
    "PCAS850L2R6	21	0.11%",
    "PCAS1000L1R3	21	0.11%",
    "PCAS999L2R1	20	0.10%",
    "PCAS750L3R6	20	0.10%",
    "PCAS716L2R7	19	0.10%",
    "PCAS863L1R2	19	0.10%",
    "PCAS889L1R6	18	0.09%",
    "PCAS836L2R4	17	0.09%",
    "PCAS913L1R6	17	0.09%",
    "PCAS723L3R2	16	0.08%",
    "PCAS723L2R4	16	0.08%",
    "PCAS850L2R4	15	0.08%",
    "PCAS697L2R4	14	0.07%",
    "PCAS749L2R1	14	0.07%",
    "PCAS716L2R8	14	0.07%",
    "PCAS723L3R1	13	0.07%",
    "PCAS863L1R1	13	0.07%",
    "PCAS914L1R4	13	0.07%",
    "PCAS750L2R1	13	0.07%",
    "PCAS803L2R1	12	0.06%",
    "PCAS836L6R2	11	0.06%",
    "PCAS913L1R4	11	0.06%",
    "PCAS678L3R2	11	0.06%",
    "PCAS914L1R3	11	0.06%",
    "PCAS837L2R7	11	0.06%",
    "PCAS867L1R2	11	0.06%",
    "PCAS792L1R4	10	0.05%",
    "PCAS1000L1R2	9	0.05%",
    "PCAS810L1R4	9	0.05%",
    "PCAS749L1R1	9	0.05%",
    "PCAS826P1R1	9	0.05%",
    "PCAS850L3R1	9	0.05%",
    "PCAS750L3R3	9	0.05%",
    "PCAS841L1R2	9	0.05%",
    "PCAS837L2R2	8	0.04%",
    "PCAS867L1R4	8	0.04%",
    "PCAS810L1R1	7	0.04%",
    "PCAS1015L1R1	7	0.04%",
    "PCAS822L2R3	6	0.03%",
    "PCAS822L2R2	6	0.03%",
    "PCAS765P2R1	5	0.03%",
    "PCAS792L1R1	5	0.03%",
    "PCAS837L1R4	5	0.03%",
    "PCAS987L1R1	5	0.03%",
    "PCAS837L2R6	5	0.03%",
    "PCAS836L1R1	5	0.03%",
    "PCAS679P2R1	5	0.03%",
    "PCAS1015L2R1	5	0.03%",
    "PCAS836L2R3	5	0.03%",
    "PCAS841L1R1	5	0.03%",
    "PCAS723L5R2	5	0.03%",
    "PCAS1014L2R1	5	0.03%",
    "PCAS889L1R5	4	0.02%",
    "PCAS851L1R4	4	0.02%",
    "PCAS1001L2R1	4	0.02%",
    "PCAS833L2R3	4	0.02%",
    "PCAS716L5R2	4	0.02%",
    "PCAS793L2R2	4	0.02%",
    "PCAS799L2R1	4	0.02%",
    "PCAS810L1R5	3	0.02%",
    "PCAS840P2R1	3	0.02%",
    "PCAS841P2R1	3	0.02%",
    "PCAS986P2R1	3	0.02%",
    "PCAS723P1R2	3	0.02%",
    "PCAS833L2R2	3	0.02%",
    "PCAS65535L255R255	3	0.02%",
    "PCAS974L4R1	3	0.02%",
    "PCAS973L1R3	3	0.02%",
    "PCAS996L1R1	3	0.02%",
    "PCAS678P2R1	3	0.02%",
    "PCAS838L1R2	3	0.02%",
    "PCAS974L1R1	2	0.01%",
    "PCAS867L1R6	2	0.01%",
    "PCAS903P2R1	2	0.01%",
    "PCAS958L1R1	2	0.01%",
    "PCAS867P3R1	2	0.01%",
    "PCAS770P1R1	2	0.01%",
    "PCAS678L3R1	2	0.01%",
    "PCAS844P2R1	2	0.01%",
    "PCAS836L5R1	2	0.01%",
    "PCAS1001L1R1	2	0.01%",
    "PCAS973L1R2	2	0.01%",
    "PCAS750L4R1	2	0.01%",
    "PCAS803L1R2	1	0.01%",
    "PCAS973P2R1	1	0.01%",
    "PCAS723P2R4	1	0.01%",
    "PCAS915P1R1	1	0.01%",
    "PCAS803P1R1	1	0.01%",
    "PCAS822P2R1	1	0.01%",
    "PCAS716P2R3	1	0.01%",
    "PCAS973P3R1	1	0.01%",
    "PCAS1010P1R1	1	0.01%",
    "PCAS912P1R1	1	0.01%",
    "PCAS913L1R1	1	0.01%",
    "PCAS805P2R1	1	0.01%",
    "PCAS858L3R1	1	0.01%",
    "PCAS953L1R1	1	0.01%",
    "PCAS697L1R3	1	0.01%",
    "PCAS793L2R1	1	0.01%",
    "PCAS810P1R1	1	0.01%",
    "PCAS961P1R1	1	0.01%",
    "PCAS1011P1R1	1	0.01%",
    "PCAS889L1R1	1	0.01%",
    "PCAS1008P1R1	1	0.01%",
    "PCAS1008L1R1	1	0.01%",
    "PCAS679P1R1	1	0.01%"
    ]

    import re
    ul = []
    for p in pl:
        pcas = re.search(r'\d+', p).group()
        plat = GetPlatform( pcas )
        if plat == None and pcas != '65535':
            ul.append( pcas )
    myset = set(ul)
    pl = sorted(myset, key=int)
    print pl
    jsonObjs = Common.GetJsonObjects( kPcasLookupTable )
    pcasTable = jsonObjs[kPcasTableName]
    for p in pl:
        newObj = {}
        newObj["description"] = ""
        newObj["name"] = ""
        newObj["platform"] = "secondary"
        pcasTable[p] = newObj

    Common.CreateJsonFile( jsonObjs, kPcasLookupTable )

UpdatePcasInfoFromDas()