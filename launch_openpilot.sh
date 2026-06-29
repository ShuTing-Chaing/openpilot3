#!/usr/bin/env bash
export ATHENA_HOST='ws://athena.mr-one.cn'
export API_HOST='http://vip.mr-one.cn'
# Skip onboarding on startup
echo -n "2" > /data/params/d/HasAcceptedTerms
echo -n "1.0" > /data/params/d/HasAcceptedTermsSP
echo -n "0.2.0" > /data/params/d/CompletedTrainingVersion
echo -n "1.0" > /data/params/d/CompletedSunnylinkConsentVersion  # Sunnylink 同意
echo -n "1" > /data/params/d/IsMetric
echo -n "zh-CHS" > /data/params/d/LanguageSetting

# Quick Start: create/remove prebuilt marker based on params
if [ -f /data/params/d/dp_dev_quick_start ] && [ "$(cat /data/params/d/dp_dev_quick_start)" = "1" ]; then
  touch ./prebuilt
else
  rm -f ./prebuilt
fi

exec ./launch_chffrplus.sh
