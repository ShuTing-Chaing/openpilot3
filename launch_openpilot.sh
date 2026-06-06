#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
export ATHENA_HOST='ws://athena.mr-one.cn'
export API_HOST='http://res.mr-one.cn'


# Skip onboarding on startup
echo -n "2" > /data/params/d/HasAcceptedTerms
echo -n "1.0" > /data/params/d/HasAcceptedTermsSP
echo -n "0.2.0" > /data/params/d/CompletedTrainingVersion
# 自动部署/修复 frpc（幂等，可重复执行

exec ./launch_chffrplus.sh