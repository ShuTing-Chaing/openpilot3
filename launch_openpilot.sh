#!/usr/bin/env bash

# custom op script
if [ -f /data/custom_op_script.sh ]; then
  source /data/custom_op_script.sh
fi

# if [[ "$(cat /data/params_cp/d/EnableConnect)" == "2" ]]; then
#   export API_HOST="https://api.carrotpilot.app"
#   export ATHENA_HOST="wss://athena.carrotpilot.app"
# fi
exec ./launch_chffrplus.sh
