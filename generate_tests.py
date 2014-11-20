from jinja2 import Template
from wurfl import devices
from pywurfl.ql import QL
import os
import yaml

base_dir = os.path.dirname(os.path.realpath(__file__))


def loadFile(filepath):
    with open (filepath, "r") as file:
        data=file.read()
    return data

def saveFile(filename, content):
    savePath = os.path.join(base_dir, 'tests', filename + '.vtc')
    with open(savePath, "w") as file:
        file.write(content)

def loadTemplate():
    template_file = os.path.join(base_dir, 'template', 'varnish_test.vtc')
    return Template(loadFile(template_file))

def run():
    generateDesktopTests()
    generateMobileTests()

def generateDesktopTests():
    renderer = loadTemplate()
    desktop_user_agents = os.path.join(base_dir, 'agents', 'desktop.yml')
    f = open(desktop_user_agents)
    desktop_browser = yaml.safe_load(f)
    f.close()

    for id, browser in desktop_browser.iteritems():
        test = renderer.render(agent=browser['ua'], device=browser['type'])
        saveFile(id, test)

def generateMobileTests():
    query = QL(devices)
    renderer = loadTemplate()

    q_dev = u"""select device where streaming_mp4 = true"""
    num = 0
    for device in devices.query(q_dev):
        # skip generic devices
        if 'generic' in device.devid:
            continue

        # skip invalid user-agents
        if 'DO_NOT_MATCH' in device.devua:
            continue

        num += 1
        print num
        deviceType = 'tablet' if device.is_tablet is True else 'mobile'
        test = renderer.render(agent=device.devua, device=deviceType)
        saveFile(device.devid, test)

run()
