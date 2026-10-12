import argparse
import json
import re
import socket
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description='Read actual guest IGD PCI location and initialization registers; no memory writes.')
parser.add_argument('--vmid', type=int, required=True)
parser.add_argument('--output', type=Path, help='Optional private diagnostic directory')
args = parser.parse_args()
if args.vmid < 100:
    parser.error('VMID must be >= 100')
directory = args.output
if directory:
    directory.mkdir(parents=True, exist_ok=True)
label = 'inspection'
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(15)
sock.connect(f'/var/run/qemu-server/{args.vmid}.qmp')
stream = sock.makefile('rwb', buffering=0)

def receive():
    while True:
        result = json.loads(stream.readline())
        if 'event' not in result:
            return result

receive()

def command(name, arguments=None):
    request = {'execute': name}
    if arguments:
        request['arguments'] = arguments
    stream.write((json.dumps(request) + '\n').encode())
    response = receive()
    if 'error' in response:
        raise RuntimeError(response)
    return response['return']

command('qmp_capabilities')
pci = command('query-pci')
qtree = command('human-monitor-command', {'command-line': 'info qtree'})

def walk(value):
    if isinstance(value, dict):
        if value.get('qdev_id') == 'hostpci0':
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

devices = list(walk(pci))
assert len(devices) == 1
device = devices[0]
assert device['id']['vendor'] == 0x8086 and device['id']['device'] == 0x46d4
mcfg = int(re.search(r'MCFG = (\d+)', qtree).group(1))
config = mcfg + (device['bus'] << 20) + (device['slot'] << 15) + (device['function'] << 12)
lines = [f"GPU BDF {device['bus']:02x}:{device['slot']:02x}.{device['function']}; MCFG 0x{mcfg:x}; PCI config at 0x{config:x}"]
values = {}
for name, offset, count in [('VID/DID', 0, 1), ('GGC', 0x50, 1), ('BDSM Gen11+', 0xc0, 2), ('ASLS/OpRegion', 0xfc, 1)]:
    result = command('human-monitor-command', {'command-line': f'xp /{count}xw 0x{config+offset:x}'})
    lines.append(name + ': ' + result.strip())
    words = re.findall(r'0x([0-9a-fA-F]{8})', result)
    values[name] = sum(int(word, 16) << (32 * i) for i, word in enumerate(words))
assert values['VID/DID'] == 0x46d48086
if values['ASLS/OpRegion']:
    signature = command('human-monitor-command', {'command-line': f"xp /16bx 0x{values['ASLS/OpRegion']:x}"})
    lines.append('OpRegion signature bytes: ' + signature.strip())
lines.extend(line.strip() for line in qtree.splitlines() if 'x-igd-' in line)
text = '\n'.join(lines) + '\n'
print(text)
if directory:
    (directory / f'guest-igd-registers.{label}.txt').write_text(text)
    (directory / f'guest-igd-registers.{label}.json').write_text(json.dumps(values, indent=2))
    (directory / f'qmp-query-pci.{label}.json').write_text(json.dumps(pci, indent=2))
sock.close()
