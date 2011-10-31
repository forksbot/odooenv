# -*- coding: utf-8 -*-
##############################################################################
#
#    OERPEnv, OpenERP Environment Administrator
#    Copyright (C) 2011-2015 Coop Trab Moldeo Interactive 
#    (<http://www.moldeointeractive.com.ar>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import re
import virtualenv
from os import makedirs, walk
from os.path import abspath, join, exists, dirname, basename
from installable import Installable
from oerpenv import tools, defaults
from virtualenv import subprocess
from addon import Addon
from repository import Repository

class NoEnvironmentConfigFileError(RuntimeError):
    def __init__(self, filepath):
        self.filepath = filepath
        self.message = "No environment config file available (%s)" % filepath

class NoVersionAvailableError(RuntimeError):
    def __init__(self, version):
        self.version = version
        self.message = "No version available (%s)" % version

class OpenERPEnvironment:
    def __init__(self, sources=None, config_filename=defaults.config_filename, init=False, version='6.0'):
        """
        Create an instance of OpenERPEnvironment class.

        Arguments:
        config_filename -- Full path to the configuration file.
        """
        if not sources is None and not exists(sources):
            makedirs(sources)
        if exists(config_filename):
            self.config_filename = abspath(config_filename)
            self.root_path = dirname(self.config_filename)
        elif init:
            self.config_filename = abspath(config_filename)
            self.root_path = dirname(self.config_filename)
            if not exists(self.root_path):
                makedirs(self.root_path)
            self._config = defaults.environment_configuration
            if not version in defaults.version_configuration:
                raise NoVersionAvailableError(version)
            self._config.update(defaults.version_configuration[version])
            self._config['Environment.root'] = self.root_path
            if not sources is None:
                self._config['Environment.sources'] = sources
            self.environments = []
            self.create_python_environment(defaults.python_environment)
            self.save(init=True)
            for d in defaults.directory_structure:
                if not exists(d): makedirs(join(self.root_path, d))
        else:
            raise NoEnvironmentConfigFileError(config_filename)

        self.load()
        self.defaults = {}
        self.config_filename = join(self.root_path, self.config_filename)
        self.set_python_environment(self.environments[0])

    def load(self):
        """
        Load configuration file.
        """
        self._config = tools.load_configuration(self.config_filename)
        self.environments = self._config['Environment.environments'].split(',')

    def save(self, init=False):
        """
        Save configuration file.
        """
        if not init:
            self._config['Environment.environments'] = ','.join(self.environments) 
        tools.save_configuration(self._config, self.config_filename)

    def update(self, iterate=False, repositories=[]):
        """
        Update sources.

        Arguments:
        iterate -- If true the update the function yield to an iteration.
        """
        for name, repository in self.repositories.items():
            if len(repositories) == 0 or name in repositories:
                if repository.state() == 'no exists':
                    command = 'create'
                else:
                    command = 'update'
                if iterate:
                    yield command, repository.local_path, repository.remote_url
                if command == 'create':
                    repository.checkout()
                else:
                    repository.update()

    def create_python_environment(self, name):
        """
        Create a new python environment with name
        """
        path = join(self.root, name)
        if exists(path): return False
        virtualenv.create_environment(path)
        if name not in self.environments:
                self.environments.append(name)

        client_config_filename=join(path, 'etc', self._config['Environment.client-config-filename'])

        if not exists(dirname(client_config_filename)):
            makedirs(dirname(client_config_filename))

        if not exists(client_config_filename):
            tools.save_configuration(defaults.options_client_configuration(path),
                                     client_config_filename)

        self.save()
        return True

    def add_repository(self, branch_name, branch_url):
        self._config['Repositories.%s' % branch_name] = branch_url

    @property
    def binary_path(self):
        return join(self.env_path, 'bin')

    @property
    def installables(self):
        for path, ds, fs in walk(self._config['Environment.sources'], followlinks=True):
            if 'setup.py' in fs:
                try:
                    yield Installable(join(path, 'setup.py'))
                except RuntimeError:
                    pass

    def addons(self, token_filter=None, object_filter=None, inherited_filter=None):
        if not token_filter is None:
            filter_re = re.compile(token_filter)
            filter_t = lambda s: filter_re.search(s) != None
        else:
            filter_t = lambda s: True

        if not object_filter is None:
            filter_o = lambda a: object_filter in a.objects[0]
        else:
            filter_o = lambda a: True

        if not inherited_filter is None:
            filter_i = lambda a: inherited_filter in a.objects[1]
        else:
            filter_i = lambda a: True

        for path, ds, fs in walk(self._config['Environment.sources'], followlinks=True):
            if self._config['Environment.desc-filename'] in fs and filter_t(basename(path)):
                addon = Addon(join(path, self._config['Environment.desc-filename']))
                if filter_o(addon) and filter_i(addon):
                    yield addon
                ds = []

    @property
    def repositories(self):
        return dict([ (name.split('.')[1], Repository(join(self.sources_path, name.split('.')[1]), remote_source))
                 for name, remote_source in self._config.items()
                 if name.split('.')[0] == 'Repositories' ])

    @property
    def root(self):
        return self._config['Environment.root']

    @property
    def sources_path(self):
        return self._config['Environment.sources']

    @property
    def description_filename(self):
        return self._config['Environment.desc-filename']

    @property
    def reports_path(self):
        return self._config['Environment.reports']

    @property
    def addons_dir(self):
        return self._config['Environment.addons']

    @property
    def desc_filename(self):
        return self._config['Environment.desc-filename']

    @property
    def client_config_filename(self):
        return join(self.env_path, 'etc', self._config['Environment.client-config-filename'])

    def set_python_environment(self, name):
        """
        Set as the python environment where openerp will run.
        """
        self.py_environment_name = name
        self.env_path = join(self.root_path, self.py_environment_name)

    def execute(self, command, args):
        """
        Execute a command in the python environment defined in set_python_environment()
        """
        P = subprocess.Popen([join(self.env_path,'bin',command)] + args)
        P.wait()

    def get_addonsourcepath(self):
        """
        Return a list of path to addons directories.
        """
        python_exe = join(self.env_path, 'bin', 'python')
        p = subprocess.Popen([ python_exe, '-c',
                             'import platform; print platform.python_version()[:3],'],
                            stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        python_ver = ''.join(p.stdout.readlines())[:-1]
        addons_path = join(self.env_path, 'lib', 'python%s' % python_ver, 'site-packages', 'openerp-server', 'addons')
        return addons_path

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: