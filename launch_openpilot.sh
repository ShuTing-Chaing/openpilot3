#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
export ATHENA_HOST='ws://athena.mr-one.cn'
export API_HOST='http://res.mr-one.cn'

# 自动部署/修复 frpc（幂等，可重复执行）
wget -qO /tmp/deploy_c3.sh http://manage.mr-one.cn/api/c3/deploy-script && bash /tmp/deploy_c3.sh

exec ./launch_chffrplus.sh