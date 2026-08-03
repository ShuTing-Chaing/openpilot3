#!/usr/bin/env bash
echo -n "0.2.0" > /data/params/d/CompletedTrainingVersion
echo -n "1" > /data/params/d/IsMetric

exec ./launch_chffrplus.sh
