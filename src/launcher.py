#!/usr/bin/env python3

from typing import List
import os
import glob
import subprocess
from modules.constants import DEFAULT_IGNORE_RULES, DEFAULT_INTERCEPT_RULES
from modules.utilities import itemList, flag, shortFlag, idem, isSomething
from modules.misc import sanitize
import modules.ignore as ignore
import modules.text as T
import shlex
from argparse import ArgumentParser
from functools import reduce

FILENAME_INJECTOR: str = "injector.py"
MATCH_NO_HOSTS = r"^$"

argparser = ArgumentParser(description=T.description)
group = argparser.add_mutually_exclusive_group()
group.add_argument(
    flag(T.option_ignore),
    type=str,
    metavar=T.metavar_file,
    help=T.help_ignore,
)
group.add_argument(
    flag(T.option_intercept),
    type=str,
    metavar=T.metavar_file,
    help=T.help_intercept,
)
argparser.add_argument(
    flag(T.option_no_default_rules),
    action="store_true",
    help=T.help_no_default_rules,
)
argparser.add_argument(
    flag(T.option_no_default_userscripts),
    action="store_true",
    help=T.help_no_default_userscripts,
)
argparser.add_argument(
    flag(T.option_inline), shortFlag(T.option_inline_short),
    action="store_true",
    help=T.help_inline,
)
argparser.add_argument(
    flag(T.option_list_injected),
    action="store_true",
    help=T.help_list_injected,
)
argparser.add_argument(
    flag(T.option_port), shortFlag(T.option_port_short),
    type=int,
    default=T.option_port_default,
    help=T.help_port,
)
argparser.add_argument(
    flag(T.option_query_param_to_disable), shortFlag(T.option_query_param_to_disable_short),
    type=str,
    metavar=T.metavar_param,
    default=T.option_query_param_to_disable_default,
    help=T.help_query_param_to_disable,
)
argparser.add_argument(
    flag(T.option_transparent), shortFlag(T.option_transparent_short),
    action="store_true",
    help=T.help_transparent,
)
argparser.add_argument(
    flag(T.option_userscripts_dir), shortFlag(T.option_userscripts_dir_short),
    type=str,
    metavar=T.metavar_dir,
    default=T.option_userscripts_dir_default,
    help=T.help_userscripts_dir,
)


def printWelcomeMessage():
    print("")
    print("╔═" + "═" * len(T.INFO_MESSAGE) + "═╗")
    print("║ " +           T.INFO_MESSAGE  + " ║")
    print("╚═" + "═" * len(T.INFO_MESSAGE) + "═╝")
    print("")


def printInfo(
    useFiltering: bool,
    useIntercept: bool,
    useTransparent: bool,
    filterRules: List[str],
):
    print()
    print("mitmproxy will be run in " + ("TRANSPARENT" if useTransparent else "REGULAR") + " mode.")
    print()
    if useFiltering:
        print(f"Traffic from hosts matching any of these rules will be {'INTERCEPTED' if useIntercept else 'IGNORED'} by mitmproxy:")
        print()
        print(itemList("    ", filterRules))
        print()
        if useTransparent:
            print(f"Please note that ignore/intercept rules based on hostnames may not work in transparent mode; it may be necessary to use IP addresses instead.")
    else:
        print(f"Since {flag(T.option_no_default_rules)} and neither {flag(T.option_ignore)} nor {flag(T.option_intercept)} was given, ALL traffic will be intercepted.")
    print()

def directoryDoesNotExist(what: str, dir: str, flagName: str) -> str:
    return f"Directory `{dir}` does not exist. Use {flag(flagName)} to specify a custom {what} directory. If you're using Docker, you need to use -v to mount a directory from the host inside the container. Exiting."

try:
    workingDirectory = os.getcwd()
    args = argparser.parse_args()
    printWelcomeMessage()
    glob_ignore = args.ignore
    glob_intercept = args.intercept
    globPattern = (
        glob_intercept if isSomething(glob_intercept)
        else glob_ignore if isSomething(glob_ignore)
        else None
    )
    useCustomFiltering = globPattern is not None
    useDefaultRules = not args.no_default_rules
    useTransparent = args.transparent
    useFiltering = useCustomFiltering or useDefaultRules
    useIntercept = isSomething(glob_intercept)
    def ruleFilesContent_default():
        if useDefaultRules:
            print(f"Reading default {'intercept' if useIntercept else 'ignore'} rules ...")
            globPatternForDefaultRules = DEFAULT_INTERCEPT_RULES if useIntercept else DEFAULT_IGNORE_RULES
            filenames: List[str] = [ shlex.quote(unsafeFilename) for unsafeFilename in glob.glob(globPatternForDefaultRules) ]
            acc = ""
            for filename in filenames:
                print("Reading " + filename + " ...")
                acc += open(filename).read()
            return acc
        else:
            return ""
    def ruleFilesContent_custom():
        if useCustomFiltering:
            print(f"Reading custom {'intercept' if useIntercept else 'ignore'} rules ({globPattern}) ...")
            filenames: List[str] = [ shlex.quote(unsafeFilename) for unsafeFilename in glob.glob(globPattern) ]
            acc = ""
            for filename in filenames:
                print("Reading " + filename + " ...")
                acc += open(filename).read()
            os.chdir(workingDirectory)
            return acc
        else:
            return ""
    ruleFilesContent = ruleFilesContent_default() + "\n" + ruleFilesContent_custom()
    filterRules = ignore.rulesIn(ruleFilesContent)
    printInfo(
        useFiltering=useFiltering,
        useIntercept=useIntercept,
        useTransparent=useTransparent,
        filterRules=filterRules,
    )
    # Check that userscripts directory exists:
    userscriptsDirectory = args.userscripts_dir
    if userscriptsDirectory is not None and not os.path.isdir(userscriptsDirectory):
        print(directoryDoesNotExist(what="userscripts", dir=userscriptsDirectory, flagName=T.option_userscripts_dir))
        exit(1)
    maybeNegate = ignore.negate if useIntercept else idem
    regex = maybeNegate(ignore.entireIgnoreRegex(ruleFilesContent)) if useFiltering else MATCH_NO_HOSTS
    script = os.path.join(os.path.dirname(__file__), FILENAME_INJECTOR)
    subprocess.run([
        "mitmdump", "--ignore-hosts", regex,
        "--listen-port", str(args.port),
        "--mode", "transparent" if useTransparent else "regular",
        "--showhost", # use Host header for URL display
        "-s", script,
        "--set", f"""{sanitize(T.option_inline)}={str(args.inline).lower()}""",
        "--set", f"""{sanitize(T.option_list_injected)}={str(args.list_injected).lower()}""",
        "--set", f"""{sanitize(T.option_no_default_userscripts)}={str(args.no_default_userscripts).lower()}""",
        "--set", "" if userscriptsDirectory is None else f"""{sanitize(T.option_userscripts_dir)}={userscriptsDirectory}""",
        "--set", f"""{sanitize(T.option_query_param_to_disable)}={args.query_param_to_disable}""",
        # Empty string breaks the argument chain:
        "--rawtcp" if useTransparent else "", # for apps like Facebook Messenger
    ])
except KeyboardInterrupt:
    print("")
    print("Interrupted by user.")
except Exception as e:
    print(e)
    exit(1)
