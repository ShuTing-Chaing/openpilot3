"""Read nl80211 capabilities with system headers; no installed packages needed."""
import argparse
import errno
import json
import os
from pathlib import Path
import socket
import struct
import subprocess

CONSTANTS = '''NL80211_CMD_GET_WIPHY NL80211_CMD_GET_INTERFACE NL80211_CMD_GET_REG NL80211_CMD_GET_SURVEY
NL80211_CMD_NEW_INTERFACE NL80211_CMD_DEL_INTERFACE NL80211_ATTR_WIPHY NL80211_ATTR_WIPHY_NAME
NL80211_ATTR_IFINDEX NL80211_ATTR_IFNAME NL80211_ATTR_IFTYPE NL80211_ATTR_SUPPORTED_IFTYPES
NL80211_ATTR_INTERFACE_COMBINATIONS NL80211_ATTR_WIPHY_BANDS NL80211_ATTR_SPLIT_WIPHY_DUMP
NL80211_ATTR_REG_ALPHA2 NL80211_ATTR_SURVEY_INFO NL80211_IFACE_COMB_LIMITS NL80211_IFACE_COMB_MAXNUM
NL80211_IFACE_COMB_NUM_CHANNELS NL80211_IFACE_LIMIT_MAX NL80211_IFACE_LIMIT_TYPES
NL80211_BAND_ATTR_FREQS NL80211_BAND_ATTR_HT_CAPA NL80211_BAND_ATTR_VHT_CAPA
NL80211_FREQUENCY_ATTR_FREQ NL80211_FREQUENCY_ATTR_DISABLED NL80211_FREQUENCY_ATTR_NO_IR
NL80211_FREQUENCY_ATTR_RADAR NL80211_FREQUENCY_ATTR_MAX_TX_POWER NL80211_SURVEY_INFO_FREQUENCY
NL80211_SURVEY_INFO_NOISE NL80211_SURVEY_INFO_IN_USE NL80211_SURVEY_INFO_TIME
NL80211_SURVEY_INFO_TIME_BUSY NL80211_IFTYPE_AP NL80211_IFTYPE_STATION
NL80211_ATTR_WIPHY_FREQ NL80211_ATTR_CHANNEL_WIDTH NL80211_ATTR_CENTER_FREQ1'''.split()


def attrs(data):
    out = {}
    while len(data) >= 4:
        length, kind = struct.unpack_from('<HH', data)
        if length < 4 or length > len(data):
            raise ValueError('Malformed netlink attribute')
        out[kind & 0x3fff] = data[4:length]
        data = data[(length + 3) & ~3:]
    return out


def attr(kind, data):
    value = struct.pack('<HH', len(data) + 4, kind) + data
    return value + b'\0' * (-len(value) % 4)


def number(value):
    return int.from_bytes(value, 'little') if value else 0


class Netlink:
    def __init__(self):
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 16)
        self.sock.bind((0, 0)); self.sock.settimeout(3); self.seq = 0
        self.family = number(self.request(16, 3, attr(2, b'nl80211\0'))[0][1])

    def request(self, family, cmd, data=b'', dump=False, ack=False):
        self.seq += 1
        flags = 1 | (0x300 if dump else 0) | (4 if ack else 0)
        body = struct.pack('<BBH', cmd, 1, 0) + data
        self.sock.sendto(struct.pack('<IHHII', 16 + len(body), family, flags, self.seq, 0) + body, (0, 0))
        results = []
        while True:
            buf = self.sock.recv(262144)
            while len(buf) >= 16:
                size, kind, _, seq, _ = struct.unpack_from('<IHHII', buf)
                body = buf[16:size]; buf = buf[(size + 3) & ~3:]
                if seq != self.seq:
                    continue
                if kind == 2:
                    error = struct.unpack_from('<i', body)[0]
                    if error:
                        raise OSError(-error, os.strerror(-error))
                    return results
                if kind == 3:
                    return results
                results.append(attrs(body[4:]))
                if not dump and not ack:
                    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--action', choices=['read', 'create', 'delete'], default='read')
    parser.add_argument('--phy', type=int, default=0)
    args = parser.parse_args(); args.work.mkdir(exist_ok=True)
    source = '#include <linux/nl80211.h>\n#include <stdio.h>\nint main(void){puts("{");\n'
    for i, name in enumerate(CONSTANTS):
        source += 'printf("\\"' + name + '\\":%d' + (',' if i + 1 < len(CONSTANTS) else '') + '\\n",' + name + ');\n'
    source += 'puts("}");return 0;}\n'
    cfile, binary = args.work / 'constants.c', args.work / 'constants'
    cfile.write_text(source)
    subprocess.run(['cc', '-O2', str(cfile), '-o', str(binary)], check=True)
    const = json.loads(subprocess.check_output([str(binary)], text=True))
    (args.work / 'constants.json').write_text(json.dumps(const, indent=2) + '\n')
    n = Netlink()
    def get(cmd, data=b'', dump=False):
        return n.request(n.family, const[cmd], data, dump)
    if args.action != 'read':
        # Mutations are restricted to this task-owned, newly created name.
        if args.action == 'create':
            if Path('/sys/class/net/opifap0').exists():
                raise RuntimeError('opifap0 already exists; do not replace it')
            payload = attr(const['NL80211_ATTR_WIPHY'], struct.pack('<I', args.phy)) + attr(const['NL80211_ATTR_IFNAME'], b'opifap0\0') + attr(const['NL80211_ATTR_IFTYPE'], struct.pack('<I', const['NL80211_IFTYPE_AP']))
        else:
            payload = attr(const['NL80211_ATTR_IFINDEX'], struct.pack('<I', socket.if_nametoindex('opifap0')))
        command = const['NL80211_CMD_NEW_INTERFACE' if args.action == 'create' else 'NL80211_CMD_DEL_INTERFACE']
        n.request(n.family, command, payload, ack=True)
        print(json.dumps({'action': args.action, 'interface': 'opifap0', 'success': True})); return
    report = {'interfaces': [], 'phy': [], 'regulatory': [], 'survey': []}
    for value in get('NL80211_CMD_GET_INTERFACE', dump=True):
        report['interfaces'].append({name: value[const[name]].rstrip(b'\0').decode() if name == 'NL80211_ATTR_IFNAME' else number(value[const[name]])
                                     for name in ['NL80211_ATTR_IFNAME', 'NL80211_ATTR_IFINDEX', 'NL80211_ATTR_WIPHY', 'NL80211_ATTR_IFTYPE', 'NL80211_ATTR_WIPHY_FREQ', 'NL80211_ATTR_CHANNEL_WIDTH', 'NL80211_ATTR_CENTER_FREQ1'] if const[name] in value})
    for value in get('NL80211_CMD_GET_WIPHY', attr(const['NL80211_ATTR_SPLIT_WIPHY_DUMP'], b''), True):
        phy = {'index': number(value.get(const['NL80211_ATTR_WIPHY'], b'')), 'bands': [], 'combinations': []}
        if const['NL80211_ATTR_SUPPORTED_IFTYPES'] in value:
            phy['iftypes'] = list(attrs(value[const['NL80211_ATTR_SUPPORTED_IFTYPES']]))
        for group in attrs(value.get(const['NL80211_ATTR_INTERFACE_COMBINATIONS'], b'')).values():
            fields = attrs(group); limits = []
            for limit in attrs(fields.get(const['NL80211_IFACE_COMB_LIMITS'], b'')).values():
                a = attrs(limit); limits.append({'max': number(a[const['NL80211_IFACE_LIMIT_MAX']]), 'types': list(attrs(a[const['NL80211_IFACE_LIMIT_TYPES']]))})
            phy['combinations'].append({'max_interfaces': number(fields.get(const['NL80211_IFACE_COMB_MAXNUM'], b'')), 'channels': number(fields.get(const['NL80211_IFACE_COMB_NUM_CHANNELS'], b'')), 'limits': limits})
        for index, band in attrs(value.get(const['NL80211_ATTR_WIPHY_BANDS'], b'')).items():
            fields = attrs(band); frequencies = []
            for freq in attrs(fields.get(const['NL80211_BAND_ATTR_FREQS'], b'')).values():
                a = attrs(freq); frequencies.append({'mhz': number(a[const['NL80211_FREQUENCY_ATTR_FREQ']]),
                    **{k: const['NL80211_FREQUENCY_ATTR_' + k.upper()] in a for k in ['disabled', 'no_ir', 'radar']}})
            phy['bands'].append({'index': index, 'ht': number(fields.get(const['NL80211_BAND_ATTR_HT_CAPA'], b'')), 'vht': number(fields.get(const['NL80211_BAND_ATTR_VHT_CAPA'], b'')), 'frequencies': frequencies})
        if phy['bands'] or phy['combinations'] or phy.get('iftypes'):
            report['phy'].append(phy)
    for value in get('NL80211_CMD_GET_REG'):
        report['regulatory'].append(value.get(const['NL80211_ATTR_REG_ALPHA2'], b'').decode(errors='replace'))
    try:
        for value in get('NL80211_CMD_GET_SURVEY', attr(const['NL80211_ATTR_IFINDEX'], struct.pack('<I', socket.if_nametoindex('wlan0'))), True):
            a = attrs(value[const['NL80211_ATTR_SURVEY_INFO']]); report['survey'].append({name: number(a[const['NL80211_SURVEY_INFO_' + name]]) for name in ['FREQUENCY', 'NOISE', 'IN_USE', 'TIME', 'TIME_BUSY'] if const['NL80211_SURVEY_INFO_' + name] in a})
    except OSError as error:
        report['survey_error'] = str(error)
    (args.work / 'capabilities.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
