#!/usr/bin/env python3

import argparse
import glob
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import selenium
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, JavascriptException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Installation requirements (all on $PATH):
# -- latest rr
# -- git
# -- Selenium-python
#
# Run from the on-prem repo directory.

class CustomException(Exception):
    pass

TIMEOUT = 60

arg_parser = argparse.ArgumentParser(description='Run on-prem smoketests.')
arg_parser.add_argument('--headless', action='store_true',
                        help='Run browser in headless mode.')
arg_parser.add_argument("--no-pull", action='store_true', help="Don't try to pull under any circumstances")
arg_parser.add_argument('tmpdir', nargs='?', default=argparse.SUPPRESS,
                        help='The directory to run tests in (defaults to mkdtemp())')
args = arg_parser.parse_args()

if 'tmpdir' in args:
    tmpdir = args.tmpdir
else:
    tmpdir = tempfile.mkdtemp()
testdir = "%s/pernosco-submit-test"%tmpdir
tmpdir_alias = "%s/alias"%tmpdir
testdir_alias = "%s/pernosco-submit-test"%tmpdir_alias

print("Working directory: %s"%tmpdir, file=sys.stderr)
trace_dir = None
next_trace_id = 0

clean_env = dict(os.environ, _RR_TRACE_DIR=tmpdir)

def build():
    subprocess.check_call(['./build.sh'], cwd=testdir)

def record():
    global trace_dir
    global next_trace_id
    subprocess.check_call(['rr', 'record', '%s/out/main'%testdir], env=clean_env)
    trace_dir = "%s/main-%d"%(tmpdir, next_trace_id)
    next_trace_id += 1

driver = None
storage_dir = "%s/storage"%tmpdir

def create_driver():
    global driver
    options = webdriver.firefox.webdriver.Options()
    if args.headless:
        if int(selenium.__version__[0]) >= 4:
            options.add_argument("-headless")
        else:
            options.set_headless()

    options.set_preference("network.websocket.delay-failed-reconnects", False)
    options.set_preference("devtools.console.stdout.content", True)
    options.log.level = "trace"
    driver = webdriver.firefox.webdriver.WebDriver(options=options)

def open_browser(url):
    retries = 0
    while True:
        retries += 1
        if retries > 100:
            print("Too many retries loading %s, bailing out"%url, file=sys.stderr)
            raise CustomException("Too many retries")

        try:
            driver.get(url)
        except WebDriverException:
            # The server may not be up yet
            time.sleep(0.05)
            continue
        break

def focus_search():
    # Use command key to focus search input
    actions = webdriver.ActionChains(driver)
    actions.key_down(Keys.CONTROL)
    actions.send_keys("S")
    actions.key_up(Keys.CONTROL)
    actions.perform()

class script_succeeds(object):
  """An expectation for checking that a script returns true.
  """
  def __init__(self, script, expected):
    self.script = script
    self.expected = expected

  def __call__(self, driver):
    try:
        return driver.execute_script(self.script) == self.expected
    except JavascriptException:
        return False

url = None
server = None

pernosco_cmd = ['./pernosco', '-x', '--log', 'info:/proc/self/fd/2']
if args.no_pull:
    pernosco_cmd.append('--no-pull')

def start_server():
    global url
    global server
    server = subprocess.Popen(pernosco_cmd + ['--user', '1200', 'serve', '--storage', storage_dir,
                              '--sources', "%s=%s"%(tmpdir, tmpdir_alias), '--sources', '/usr', trace_dir],
                              stdout=subprocess.PIPE, encoding='utf-8')
    url = None
    for line in server.stdout:
        print(line)
        last_word = line.split()[-1]
        if last_word.startswith("http:"):
            url = last_word
            break

test_git_revision = '84861f84a7462c2b4e04b7b41f7f83616c83c8dc'
subprocess.check_call(['git', 'clone', 'https://github.com/Pernosco/pernosco-submit-test'], cwd=tmpdir)
subprocess.check_call(['git', 'checkout', '-q', test_git_revision], cwd=testdir)
subprocess.check_call(['mkdir', '-p', testdir_alias])
print("Mounting filesystem into test")
subprocess.check_call(['sudo', 'mount', '--bind', testdir, testdir_alias])
build()
record()

if not args.no_pull:
    subprocess.check_call(['./pernosco', 'pull'])

subprocess.check_call(pernosco_cmd + ['--user', '1200', 'build', '--check-trace'], env=clean_env)

os.mkdir(storage_dir)

print("Starting server")
start_server()
print("Opening browser at ", url, " to run tests")
create_driver()
open_browser(url)
print("Browser open, running tests")
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".view.source > .viewTitle"), "_exit.c")
)
source_frame = driver.find_element_by_css_selector("#main > .view.source iframe")
main_window = driver.window_handles[0]
driver.switch_to.frame(source_frame)
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#monaco-container"), "_exit (")
)
driver.switch_to.window(main_window)

search_input = driver.find_element_by_css_selector("#searchInput")

# Test that our source file is readable
focus_search()
search_input.send_keys("helper_function")
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#searchDropdown > *:nth-child(1)"), "helper_function")
)
search_input.send_keys(Keys.RETURN)

WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#main > .execution > .contents > div"), "helper_function")
)
item = driver.find_element_by_css_selector("#main > .execution > .contents > div");
item.click();
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".view.source > .viewTitle"), "file.c")
)
driver.switch_to.frame(source_frame)
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#monaco-container"), "helper_function")
)
driver.switch_to.window(main_window)

# Test that notebook text persists
focus_search()
search_input.send_keys("notebook")
WebDriverWait(driver, TIMEOUT).until(
    EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#searchDropdown > *:nth-child(1)"), "otebook")
)
search_input.send_keys(Keys.RETURN)

first_note = driver.find_element_by_css_selector("#main > .notebook > .contents > div > div.tentative");
WebDriverWait(driver, TIMEOUT).until(
    script_succeeds("return document.querySelector('#main > .notebook > .contents > div').classList.contains('focus');", True)
)
first_note.click();
WebDriverWait(driver, TIMEOUT).until(
    script_succeeds("return document.querySelector('#main > .notebook > .contents > div > div:nth-child(2) > textarea').value;", "")
)

actions = webdriver.ActionChains(driver)
actions.send_keys("HelloKitty")
actions.perform()
WebDriverWait(driver, TIMEOUT).until(
    script_succeeds("return document.querySelector('#main > .notebook > .contents > div > div:nth-child(2) > textarea').value;", "HelloKitty")
)
# Give the appserver time to write out the data
time.sleep(2)

driver.get("about:blank")

os.kill(server.pid, signal.SIGINT)
server.wait()

start_server()
open_browser(url)
WebDriverWait(driver, TIMEOUT).until(
    script_succeeds("return document.querySelector('#main > .notebook > .contents > div > div:nth-child(2) > textarea').value;", "HelloKitty")
)

driver.quit()
os.kill(server.pid, signal.SIGINT)
server.wait()

# Check that docker containers have been cleaned up
output = subprocess.check_output(['docker', 'ps', '-aq'], encoding='utf-8').strip()
if len(output) > 0:
    print("Docker containers still running:\n%s"%output, file=sys.stderr)
    assert False

subprocess.check_call(pernosco_cmd + ['--user', '1200', 'build', '--copy-sources', '/'], env=clean_env)

zip_files = subprocess.check_output(["unzip", "-Z1", "%s/files.user/sources.zip"%trace_dir], encoding='utf-8').splitlines()
assert "%s/pernosco-submit-test/out/message.h"%tmpdir in zip_files

subprocess.check_call(['sudo', 'umount', testdir_alias])

print("\nPASS", file=sys.stderr)

# It would be nice to delete 'tmpdir' but we can't actually do that because it contains
# files and directories owned by another user (the 'pernosco' container user) :-(
