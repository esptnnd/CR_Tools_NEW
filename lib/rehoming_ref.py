import pandas as pd
# === Build ENM Mapping Dictionary ===
raw_data = """
CMI8362X;ENM-RAN1A
NKT8361X;ENM-RAN2A
NKT8362X;ENM-RAN2A
SMP8361X;ENM-RAN2A
CMI8363X;ENM-RAN3A
PSN8362X;ENM-RAN3A
CMI8361X;ENM-RAN5A
PTT8361X;ENM-RAN5A
AYT8361X;ENM-RAN4A
AYT8362X;ENM-RAN4A
PSN8361X;ENM-RAN7A
DRRST03;ENM_DTAC_FDD1
DRRST07;ENM_DTAC_FDD1
DRRST08;ENM_DTAC_FDD1
DRRST14;ENM_DTAC_FDD1
DRTBE01;ENM_DTAC_FDD1
DRTBE02;ENM_DTAC_FDD1
DRSNK03;ENM_DTAC_FDD2
DRSNK06;ENM_DTAC_FDD2
DRSNK07;ENM_DTAC_FDD2
DRSNK14;ENM_DTAC_FDD2
DRSNK15;ENM_DTAC_FDD2
DRSNK16;ENM_DTAC_FDD2
DRRST04;ENM_DTAC_FDD3
DRSNK04;ENM_DTAC_FDD3
DRSNK05;ENM_DTAC_FDD3
DRSNK08;ENM_DTAC_FDD3
DRSNK09;ENM_DTAC_FDD3
DRSNK10;ENM_DTAC_FDD3
DRSNK13;ENM_DTAC_FDD3
DRRST02;ENM_DTAC_FDD4
DRRST05;ENM_DTAC_FDD4
DRRST06;ENM_DTAC_FDD4
DRRST09;ENM_DTAC_FDD4
DRRST10;ENM_DTAC_FDD4
DRRST11;ENM_DTAC_FDD4
DRRST12;ENM_DTAC_FDD4
DRRST16;ENM_DTAC_FDD4
DRSNK01;ENM_DTAC_FDD4
DRSNK02;ENM_DTAC_FDD4
"""

# Create lookup dictionary: {'CMI8362X': 'ENM-RAN1A', ...}
enm_lookup = {
    line.split(';')[0]: line.split(';')[1]
    for line in raw_data.strip().splitlines()
}

def write_output_lac_rac(template, row , filename_prefix ):
    RNC_DTAC_LIST = pd.DataFrame({'RNC_DTAC': ['DRRST03', 'DRRST07', 'DRRST08', 'DRRST14', 'DRTBE01', 'DRTBE02', 'DRSNK03',
                                        'DRSNK06', 'DRSNK07', 'DRSNK14', 'DRSNK15', 'DRSNK16', 'DRRST04', 'DRSNK04',
                                        'DRSNK05', 'DRSNK08', 'DRSNK09', 'DRSNK10', 'DRSNK13', 'DRRST02', 'DRRST05',
                                        'DRRST06', 'DRRST09', 'DRRST10', 'DRRST11', 'DRRST12', 'DRRST16', 'DRSNK01',
                                        'DRSNK02']})    
    ##
    data_dict = row.to_dict()
    RNC_TARGET = data_dict.get('RNC_TARGET', 'UNKNOWN')
    if RNC_TARGET in RNC_DTAC_LIST['RNC_DTAC'].values:
        data_dict['SUB_FDN'] = f"SubNetwork=ONRM_ROOT_MO,SubNetwork={RNC_TARGET},MeContext={RNC_TARGET},ManagedElement=1"
    else:
        data_dict['SUB_FDN'] = f"SubNetwork={RNC_TARGET},MeContext={RNC_TARGET},ManagedElement=1"
    ###00_SCRIPT_CELL_
    ###03_SCRIPT_URA_LAC_
    enm = enm_lookup.get(RNC_TARGET, 'UNKNOWN')

    # Format isi dan tulis
    filename = f"01_output_script/{filename_prefix}_{enm}.txt"
    output_str = template.format(**data_dict)
    with open(filename, 'a') as f:
        f.write(output_str)



def write_output(template, row, filename_prefix, replace_fdn=True, filename_by='target'):
    """
    Format row dengan template, ganti FDN jika diminta, dan tulis ke file.
    Nama file akan disertai ENM name jika ditemukan di raw_data, jika tidak gunakan 'UNKNOWN'.
    """
    # Konversi baris ke dict dan bersihkan float-int
    data = {k: str(int(v)) if isinstance(v, float) and v.is_integer() else v for k, v in row.to_dict().items()}
    
    src = data.get('RNC_SOURCE', 'UNKNOWN')
    tgt = data.get('RNC_TARGET', 'UNKNOWN')

    # Ganti FDN jika diminta
    if replace_fdn:
        pattern = f"SubNetwork={src},MeContext={src},ManagedElement=1,"
        replacement = f"SubNetwork={tgt},MeContext={tgt},ManagedElement=1,"
        data = {k: v.replace(pattern, replacement) if isinstance(v, str) else v for k, v in data.items()}

    # Tentukan suffix berdasarkan filename_by
    suffix = tgt if filename_by == 'target' else src if filename_by == 'source' else 'ALL'

    # Cari ENM dari mapping
    enm = enm_lookup.get(suffix, 'UNKNOWN')

    # Format nama file
    filename = f"01_output_script/{filename_prefix}_{enm}.txt"

    # Format isi dan tulis
    output_str = template.format(**data)
    with open(filename, 'a') as f:
        f.write(output_str)



###### WRITE CMBULK SCRIPT FOR LAC RAC URA
template_URA_CREATE = """
create
FDN : {SUB_FDN},RncFunction=1,Ura={URA_PLAN}
UraId : {URA_PLAN}
uraIdentity : {URA_PLAN}
userLabel : '{URA_PLAN}'

"""

template_LAC_CREATE = """
create
FDN : {SUB_FDN},RncFunction=1,LocationArea={LAC_PLAN}
LocationAreaId : {LAC_PLAN}
att : TRUE
lac : {LAC_PLAN}
t3212 : 10
userLabel : '{LAC_PLAN}'


"""

template_RAC_CREATE = """
create
FDN : {SUB_FDN},RncFunction=1,LocationArea={LAC_PLAN},RoutingArea={RAC_PLAN}
RoutingAreaId : {RAC_PLAN}
nmo : MODE_II
rac : {RAC_PLAN}
userLabel : '{RAC_PLAN}'

"""


template_CELL = """
create
FDN : {serviceAreaRef}
ServiceAreaId : {cId}
sac : {cId}
userLabel : SAC_{cId}


create
FDN : {FDN}
UtranCellId : {UtranCellId}
absPrioCellRes : {absPrioCellRes}
accessClassesBarredCs : {accessClassesBarredCs}
accessClassesBarredPs : {accessClassesBarredPs}
accessClassNBarred : {accessClassNBarred}
admBlockRedirection : {admBlockRedirection}
administrativeState : {administrativeState}
agpsEnabled : {agpsEnabled}
amrNbSelector : {amrNbSelector}
amrWbRateDlMax : {amrWbRateDlMax}
amrWbRateUlMax : {amrWbRateUlMax}
anrIafUtranCellConfig : {anrIafUtranCellConfig}
anrIefUtranCellConfig : {anrIefUtranCellConfig}
antennaPosition : {antennaPosition}
aseDlAdm : {aseDlAdm}
aseLoadThresholdUlSpeech : {aseLoadThresholdUlSpeech}
aseUlAdm : {aseUlAdm}
autoAcbEnabled : {autoAcbEnabled}
autoAcbMaxPsClassesToBar : {autoAcbMaxPsClassesToBar}
autoAcbMinRcssrInput : {autoAcbMinRcssrInput}
autoAcbRcssrThresh : {autoAcbRcssrThresh}
autoAcbRcssrWeight : {autoAcbRcssrWeight}
autoAcbRtwpThresh : {autoAcbRtwpThresh}
bchPower : {bchPower}
cbsSchedulePeriodLength : {cbsSchedulePeriodLength}
cellBroadcastSac : {cellBroadcastSac}
cellReserved : {cellReserved}
cellUpdateConfirmCsInitRepeat : {cellUpdateConfirmCsInitRepeat}
cellUpdateConfirmPsInitRepeat : {cellUpdateConfirmPsInitRepeat}
cId : {cId}
codeLoadThresholdDlSf128 : {codeLoadThresholdDlSf128}
compModeAdm : {compModeAdm}
ctchAdmMargin : {ctchAdmMargin}
ctchOccasionPeriod : {ctchOccasionPeriod}
cyclicAcb : {cyclicAcb}
cyclicAcbCs : {cyclicAcbCs}
cyclicAcbPs : {cyclicAcbPs}
dchIflsMarginCode : {dchIflsMarginCode}
dchIflsMarginPower : {dchIflsMarginPower}
dchIflsThreshCode : {dchIflsThreshCode}
dchIflsThreshPower : {dchIflsThreshPower}
dlCodeAdm : {dlCodeAdm}
dlCodeOffloadLimit : {dlCodeOffloadLimit}
dlCodePowerCmEnabled : {dlCodePowerCmEnabled}
dlPowerOffloadLimit : {dlPowerOffloadLimit}
dmcrEnabled : {dmcrEnabled}
dnclEnabled : {dnclEnabled}
downswitchTimer : {downswitchTimer}
eulMcServingCellUsersAdmTti2 : {eulMcServingCellUsersAdmTti2}
eulNonServingCellUsersAdm : {eulNonServingCellUsersAdm}
eulServingCellUsersAdm : {eulServingCellUsersAdm}
eulServingCellUsersAdmTti2 : {eulServingCellUsersAdmTti2}
fachMeasOccaCycLenCoeff : {fachMeasOccaCycLenCoeff}
ganHoEnabled : {ganHoEnabled}
hardIfhoCorr : {hardIfhoCorr}
hcsSib3Config : {hcsSib3Config}
hcsUsage : {hcsUsage}
hoType : {hoType}
hsdpaUsersAdm : {hsdpaUsersAdm}
hsdpaUsersOffloadLimit : {hsdpaUsersOffloadLimit}
hsdschInactivityTimer : {hsdschInactivityTimer}
hsdschInactivityTimerCpc : {hsdschInactivityTimerCpc}
hsIflsDownswitchTrigg : {hsIflsDownswitchTrigg}
hsIflsHighLoadThresh : {hsIflsHighLoadThresh}
hsIflsMarginUsers : {hsIflsMarginUsers}
hsIflsPowerLoadThresh : {hsIflsPowerLoadThresh}
hsIflsRedirectLoadLimit : {hsIflsRedirectLoadLimit}
hsIflsSpeechMultiRabTrigg : {hsIflsSpeechMultiRabTrigg}
hsIflsThreshUsers : {hsIflsThreshUsers}
hsIflsTrigger : {hsIflsTrigger}
iFCong : {iFCong}
iFHyst : {iFHyst}
ifIratHoPsIntHsEnabled : {ifIratHoPsIntHsEnabled}
iflsCpichEcnoThresh : {iflsCpichEcnoThresh}
iflsMode : {iflsMode}
iflsRedirectUarfcn : {iflsRedirectUarfcn}
inactivityTimeMultiPsInteractive : {inactivityTimeMultiPsInteractive}
inactivityTimer : {inactivityTimer}
inactivityTimerEnhUeDrx : {inactivityTimerEnhUeDrx}
inactivityTimerPch : {inactivityTimerPch}
individualOffset : {individualOffset}
interFreqFddMeasIndicator : {interFreqFddMeasIndicator}
interPwrMax : {interPwrMax}
interRate : {interRate}
iubLinkRef : '{iubLinkRef}'
loadBasedHoSupport : {loadBasedHoSupport}
loadBasedHoType : {loadBasedHoType}
loadSharingGsmFraction : {loadSharingGsmFraction}
loadSharingGsmThreshold : {loadSharingGsmThreshold}
loadSharingMargin : {loadSharingMargin}
localCellId : {localCellId}
locationAreaRef : '{locationAreaRef}'
lteMeasEnabled : {lteMeasEnabled}
maximumTransmissionPower : {maximumTransmissionPower}
maxPwrMax : {maxPwrMax}
maxRate : {maxRate}
maxTxPowerUl : {maxTxPowerUl}
minimumRate : {minimumRate}
minPwrMax : {minPwrMax}
minPwrRl : {minPwrRl}
mocnCellProfileRef : '{mocnCellProfileRef}'
nOutSyncInd : {nOutSyncInd}
pagingPermAccessCtrl : {pagingPermAccessCtrl}
pathlossThreshold : {pathlossThreshold}
prefMobilityToLteCsfbHandling : {prefMobilityToLteCsfbHandling}
primaryCpichPower : {primaryCpichPower}
primarySchPower : {primarySchPower}
primaryScramblingCode : {primaryScramblingCode}
primaryTpsCell : {primaryTpsCell}
psHoToLteEnabled : {psHoToLteEnabled}
pwrAdm : {pwrAdm}
pwrLoadThresholdDlSpeech : {pwrLoadThresholdDlSpeech}
qHyst1 : {qHyst1}
qHyst2 : {qHyst2}
qQualMin : {qQualMin}
qRxLevMin : {qRxLevMin}
qualMeasQuantity : {qualMeasQuantity}
rachOverloadProtect : {rachOverloadProtect}
rateSelectionPsInteractive : {rateSelectionPsInteractive}
redirectUarfcn : {redirectUarfcn}
releaseRedirect : {releaseRedirect}
releaseRedirectEutraTriggers : {releaseRedirectEutraTriggers}
releaseRedirectHsIfls : {releaseRedirectHsIfls}
reportingRange1a : {reportingRange1a}
reportingRange1b : {reportingRange1b}
rlFailureT : {rlFailureT}
routingAreaRef : '{routingAreaRef}'
rrcLcEnabled : {rrcLcEnabled}
rwrEutraCc : {rwrEutraCc}
rwrEutraLteMeas : {rwrEutraLteMeas}
secondaryCpichPower : {secondaryCpichPower}
secondarySchPower : {secondarySchPower}
servDiffRrcAdmHighPrioProfile : {servDiffRrcAdmHighPrioProfile}
serviceAreaRef : '{serviceAreaRef}'
serviceRestrictions : {serviceRestrictions}
sf128Adm : {sf128Adm}
sf16Adm : {sf16Adm}
sf16AdmUl : {sf16AdmUl}
sf16gAdm : {sf16gAdm}
sf32Adm : {sf32Adm}
sf4AdmUl : {sf4AdmUl}
sf64AdmUl : {sf64AdmUl}
sf8Adm : {sf8Adm}
sf8AdmUl : {sf8AdmUl}
sf8gAdmUl : {sf8gAdmUl}
sHcsRat : {sHcsRat}
sib11UtranCellConfig : {sib11UtranCellConfig}
sib1PlmnScopeValueTag : {sib1PlmnScopeValueTag}
sInterSearch : {sInterSearch}
sIntraSearch : {sIntraSearch}
spare : {spare}
spareA : {spareA}
sRatSearch : {sRatSearch}
srbAdmExempt : {srbAdmExempt}
standAloneSrbSelector : {standAloneSrbSelector}
tCell : {tCell}
timeToTrigger1a : {timeToTrigger1a}
timeToTrigger1b : {timeToTrigger1b}
tpsCellThresholds : {tpsCellThresholds}
transmissionScheme : {transmissionScheme}
treSelection : {treSelection}
uarfcnDl : {uarfcnDl}
uarfcnUl : {uarfcnUl}
updateLocator : {updateLocator}
uraRef : [{uraRef}]
usedFreqThresh2dEcno : {usedFreqThresh2dEcno}
usedFreqThresh2dRscp : {usedFreqThresh2dRscp}
userLabel : {userLabel}
utranCellPosition : {utranCellPosition}
"""



template_FACH = """create
FDN : {FDN}
FachId : {FachId}
administrativeState : {administrativeState}
maxFach1Power : {maxFach1Power}
maxFach2Power : {maxFach2Power}
pOffset1Fach : {pOffset1Fach}
pOffset3Fach : {pOffset3Fach}
sccpchOffset : {sccpchOffset}
userLabel : '{userLabel}'


"""

template_Hsdsch = """create
FDN : {FDN}
HsdschId : {HsdschId}
administrativeState : {administrativeState}
codeThresholdPdu656 : {codeThresholdPdu656}
cqiFeedbackCycle : {cqiFeedbackCycle}
deltaAck1 : {deltaAck1}
deltaAck2 : {deltaAck2}
deltaCqi1 : {deltaCqi1}
deltaCqi2 : {deltaCqi2}
deltaNack1 : {deltaNack1}
deltaNack2 : {deltaNack2}
hsMeasurementPowerOffset : {hsMeasurementPowerOffset}
initialAckNackRepetitionFactor : {initialAckNackRepetitionFactor}
initialCqiRepetitionFactor : {initialCqiRepetitionFactor}
numHsPdschCodes : {numHsPdschCodes}
numHsScchCodes : {numHsScchCodes}
userLabel : '{userLabel}'


"""


template_Pch = """create
FDN : {FDN}
PchId : {PchId}
administrativeState : {administrativeState}
pchPower : {pchPower}
pichPower : {pichPower}
sccpchOffset : {sccpchOffset}
userLabel : '{userLabel}'


"""



template_Rach = """create
FDN : {FDN}
RachId : {RachId}
administrativeState : {administrativeState}
aichPower : {aichPower}
aichTransmissionTiming : {aichTransmissionTiming}
constantValueCprach : {constantValueCprach}
increasedRachCoverageEnabled : {increasedRachCoverageEnabled}
maxPreambleCycle : {maxPreambleCycle}
nb01Max : {nb01Max}
nb01Min : {nb01Min}
powerOffsetP0 : {powerOffsetP0}
powerOffsetPpm : {powerOffsetPpm}
preambleRetransMax : {preambleRetransMax}
preambleSignatures : {preambleSignatures}
scramblingCodeWordNo : {scramblingCodeWordNo}
spreadingFactor : {spreadingFactor}
subChannelNo : {subChannelNo}
userLabel : '{userLabel}'


"""

template_EUL = """create
FDN : {FDN}
EulId : {EulId}
administrativeState : {administrativeState}
eulDchBalancingEnabled : {eulDchBalancingEnabled}
eulDchBalancingLoad : {eulDchBalancingLoad}
eulDchBalancingOverload : {eulDchBalancingOverload}
eulDchBalancingReportPeriod : {eulDchBalancingReportPeriod}
eulDchBalancingSuspendDownSw : {eulDchBalancingSuspendDownSw}
eulDchBalancingTimerNg : {eulDchBalancingTimerNg}
eulLoadTriggeredSoftCong : {eulLoadTriggeredSoftCong}
eulMaxTargetRtwp : {eulMaxTargetRtwp}
numEagchCodes : {numEagchCodes}
numEhichErgchCodes : {numEhichErgchCodes}
pathlossThresholdEulTti2 : {pathlossThresholdEulTti2}
releaseAseUlNg : {releaseAseUlNg}
threshEulTti2Ecno : {threshEulTti2Ecno}
userLabel : '{userLabel}'


"""


template_IUBLINK = """create
FDN : {FDN}
IubLinkId : {IubLinkId}
administrativeState : {administrativeState}
atmUserPlaneTermSubrackRef : {atmUserPlaneTermSubrackRef}
controlPlaneTransportOption : {controlPlaneTransportOption}
dlHwAdm : {dlHwAdm}
l2EstReqRetryTimeNbapC : {l2EstReqRetryTimeNbapC}
l2EstReqRetryTimeNbapD : {l2EstReqRetryTimeNbapD}
linkType : {linkType}
rbsId : {rbsId}
remoteCpIpAddress1 : {remoteCpIpAddress1}
remoteCpIpAddress2 : {remoteCpIpAddress2}
rncModuleAllocWeight : {rncModuleAllocWeight}
rncModulePreferredRef : {rncModulePreferredRef}
rSiteRef : {rSiteRef}
softCongThreshGbrBwDl : {softCongThreshGbrBwDl}
softCongThreshGbrBwUl : {softCongThreshGbrBwUl}
spare : {spare}
spareA : {spareA}
ulHwAdm : {ulHwAdm}
userLabel : '{userLabel}'
userPlaneGbrAdmBandwidthDl : {userPlaneGbrAdmBandwidthDl}
userPlaneGbrAdmBandwidthUl : {userPlaneGbrAdmBandwidthUl}
userPlaneGbrAdmEnabled : {userPlaneGbrAdmEnabled}
userPlaneGbrAdmMarginDl : {userPlaneGbrAdmMarginDl}
userPlaneGbrAdmMarginUl : {userPlaneGbrAdmMarginUl}
userPlaneIpResourceRef : {userPlaneIpResourceRef}
userPlaneTransportOption : {userPlaneTransportOption}


"""



template_IUBLINK = """create
FDN : {FDN}
IubLinkId : {IubLinkId}
administrativeState : {administrativeState}
atmUserPlaneTermSubrackRef : '{atmUserPlaneTermSubrackRef}'
controlPlaneTransportOption : {controlPlaneTransportOption}
dlHwAdm : {dlHwAdm}
l2EstReqRetryTimeNbapC : {l2EstReqRetryTimeNbapC}
l2EstReqRetryTimeNbapD : {l2EstReqRetryTimeNbapD}
linkType : {linkType}
rbsId : {rbsId}
remoteCpIpAddress1 : '{remoteCpIpAddress1}'
remoteCpIpAddress2 : '{remoteCpIpAddress2}'
rncModuleAllocWeight : {rncModuleAllocWeight}
rncModulePreferredRef : [{rncModulePreferredRef}]
rSiteRef : [{rSiteRef}]
softCongThreshGbrBwDl : {softCongThreshGbrBwDl}
softCongThreshGbrBwUl : {softCongThreshGbrBwUl}
spare : {spare}
spareA : {spareA}
ulHwAdm : {ulHwAdm}
userLabel : '{userLabel}'
userPlaneGbrAdmBandwidthDl : {userPlaneGbrAdmBandwidthDl}
userPlaneGbrAdmBandwidthUl : {userPlaneGbrAdmBandwidthUl}
userPlaneGbrAdmEnabled : {userPlaneGbrAdmEnabled}
userPlaneGbrAdmMarginDl : {userPlaneGbrAdmMarginDl}
userPlaneGbrAdmMarginUl : {userPlaneGbrAdmMarginUl}
userPlaneIpResourceRef : '{userPlaneIpResourceRef}'
userPlaneTransportOption : {userPlaneTransportOption}


"""


template_IUBLINK_EDCH = """
create
FDN : {FDN}
IubEdchId : {IubEdchId}
edchDataFrameDelayThreshold : {edchDataFrameDelayThreshold}
userLabel : '{userLabel}'


"""



template_EutranFreqRelation = """create
FDN : {FDN}
EutranFreqRelationId : {EutranFreqRelationId}
barredCnOperatorRef : [{barredCnOperatorRef}]
blacklistedCell : []
cellReselectionPriority : {cellReselectionPriority}
coSitedCellAvailable : {coSitedCellAvailable}
eutranFrequencyRef : '{eutranFrequencyRef}'
qQualMin : {qQualMin}
qRxLevMin : {qRxLevMin}
redirectionOrder : {redirectionOrder}
thresh2dRwr : {thresh2dRwr}
threshHigh : {threshHigh}
threshHigh2 : {threshHigh2}
threshLow : {threshLow}
threshLow2 : {threshLow2}
userLabel : '{userLabel}'



"""



