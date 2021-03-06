# AUTOGENERATED! DO NOT EDIT! File to edit: 00_core.ipynb (unless otherwise specified).

__all__ = ['GH_HOST', 'find_config', 'FastRelease', 'fastrelease_changelog', 'fastrelease_release', 'fastrelease']

# Cell
from fastcore.imports import *
from fastcore.utils import *

from datetime import datetime
from textwrap import fill
from configparser import ConfigParser
import json,subprocess
from urllib.request import HTTPError
from .fastscript import *

# Cell
GH_HOST = "https://api.github.com"

# Cell
def find_config(cfg_name="settings.ini"):
    cfg_path = Path().absolute()
    while cfg_path != cfg_path.parent and not (cfg_path/cfg_name).exists(): cfg_path = cfg_path.parent
    config_file = cfg_path/cfg_name
    assert config_file.exists(), f"Couldn't find {cfg_name}"
    config = ConfigParser()
    config.read(config_file)
    return config['DEFAULT'],cfg_path

# Cell
def _issue_txt(issue):
    res = '- {} ([#{}]({}))\n'.format(issue["title"].strip(), issue["number"], issue["html_url"])
    body = issue['body']
    if not body: return res
    return res + fill(body.strip(), initial_indent="  - ", subsequent_indent="    ") + "\n"

def _issues_txt(iss, label):
    if not iss: return ''
    res = f"### {label}\n\n"
    return res + '\n'.join(map(_issue_txt, iss))

def _load_json(cfg, k):
    try: return json.loads(cfg[k])
    except json.JSONDecodeError as e: raise Exception(f"Key: `{k}` in .ini file is not a valid JSON string: {e}")

# Cell
class FastRelease:
    def __init__(self, owner=None, repo=None, token=None, **groups):
        "Create CHANGELOG.md from GitHub issues"
        self.cfg,cfg_path = find_config()
        self.changefile = cfg_path/'CHANGELOG.md'
        if not groups:
            default_groups=dict(breaking="Breaking Changes", enhancement="New Features", bug="Bugs Squashed")
            groups=_load_json(self.cfg, 'label_groups') if 'label_groups' in self.cfg else default_groups
        os.chdir(cfg_path)
        if not owner: owner = self.cfg['user']
        if not repo:  repo  = self.cfg['lib_name']
        if not token:
            assert Path('token').exists, "Failed to find token"
            self.headers = { 'Authorization' : 'token ' + Path('token').read_text().strip() }
        self.owner,self.repo,self.groups = owner,repo,groups
        self.repo_url = f"{GH_HOST}/repos/{owner}/{repo}"

    def gh(self, path, complete=False, post=False, **data):
        "Call GitHub API `path`"
        if not complete: path = f"{self.repo_url}/{path}"
        return do_request(path, headers=self.headers, post=post, **data)

    def _tag_date(self, tag):
        try: tag_d = self.gh(f"git/ref/tags/{tag}")
        except HTTPError: raise Exception(f"Failed to find tag {tag}")
        commit_d = self.gh(tag_d["object"]["url"], complete=True)
        self.commit_date = commit_d["committer"]["date"]
        return self.commit_date

    def _issues(self, label):
        return self.gh("issues", state='closed', sort='created', filter='all',
                       since=self.commit_date, labels=label)

    def _issue_groups(self): return parallel(self._issues, self.groups.keys())
    def _latest_release(self): return self.gh("releases/latest")["tag_name"]

    def changelog(self, debug=False):
        "Create the CHANGELOG.md file, or return the proposed text if `debug` is `True`"
        if not self.changefile.exists(): self.changefile.write_text("# Release notes\n\n<!-- do not remove -->\n")
        marker = '<!-- do not remove -->\n'
        try:
            latest = self._latest_release()
            self._tag_date(latest)
        except HTTPError: # no prior releases
            self.commit_date = '2000-01-01T00:00:004Z'
        res = f"\n## {self.cfg['version']}\n"
        issues = self._issue_groups()
        res += '\n'.join(_issues_txt(*o) for o in zip(issues, self.groups.values()))
        if debug: return res
        res = self.changefile.read_text().replace(marker, marker+res+"\n")
        shutil.copy(self.changefile, self.changefile.with_suffix(".bak"))
        self.changefile.write_text(res)

    def release(self):
        "Tag and create a release in GitHub for the current version"
        ver = self.cfg['version']
        run_proc('git', 'tag', ver)
        run_proc('git', 'push', '--tags')
        run_proc('git', 'pull', '--tags')
        notes = self.latest_notes()
        if not notes.startswith(ver): notes = ''
        self.gh("releases", post=True, tag_name=ver, name=ver, body=notes)
        return ver

    def latest_notes(self):
        "Latest CHANGELOG entry"
        if not self.changefile.exists(): return ''
        its = re.split(r'^## ', self.changefile.read_text(), flags=re.MULTILINE)
        if not len(its)>0: return ''
        return its[1].strip()

# Cell
@call_parse
def fastrelease_changelog(debug:Param("Print info to be added to CHANGELOG, instead of updating file", bool_arg)=False):
    "Create a CHANGELOG.md file from closed and labeled GitHub issues"
    FastRelease().changelog(debug=debug)

# Cell
@call_parse
def fastrelease_release(token:Param("Optional GitHub token (otherwise `token` file is used)", str)=None):
    "Tag and create a release in GitHub for the current version"
    ver = FastRelease(token=token).release()
    print(f"Released {ver}")

# Cell
@call_parse
def fastrelease(debug:Param("Print info to be added to CHANGELOG, instead of updating file", bool_arg)=False,
                token:Param("Optional GitHub token (otherwise `token` file is used)", str)=None):
    "Calls `fastrelease_changelog`, lets you edit the result, then pushes to git and calls `fastrelease_release`"
    cfg,cfg_path = find_config()
    FastRelease().changelog(debug=debug)
    subprocess.run([os.environ.get('EDITOR','nano'), cfg_path/'CHANGELOG.md'])
    if not input("Make release now? (y/n) ").lower().startswith('y'): sys.exit(1)
    run_proc('git', 'commit', '-am', 'release')
    run_proc('git', 'push')
    ver = FastRelease(token=token).release()
    print(f"Released {ver}")