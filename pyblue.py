#! /usr/bin/python

# PyGreen
# Copyright (c) 2013, Nicolas Vanhoren
# 
# Released under the MIT license
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
# Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN
# AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals, print_function

import bottle
import os.path
from mako.lookup import TemplateLookup
import os, os.path, itertools
import wsgiref.handlers
import sys, logging, re
import argparse
import sys
import markdown
import waitress
import utils

_logger = logging.getLogger(__name__)

# always adds the location of the default templates

op = os.path
dn = op.dirname

class File(object):
    "Represents a file object within PyBlue"

    def __init__(self, fname, root):
        self.root  = root
        self.fname = fname
        self.fpath = os.path.join(root, fname)
        self.dname = dn(self.fpath)
        self.ext   = os.path.splitext(fname)[1]

        self.meta  =  dict(name=self.nice_name, sortkey="2", tags=set("data"))
        if not self.skip_file:
            self.meta.update(utils.parse_meta(self.fpath))

    @property
    def nice_name(self):
        "Attempts to generate a nicer name from the filename"
        head, tail = os.path.split(self.fname)
        base, ext = os.path.splitext(tail)
        name = base.title().replace("-", " ").replace("_", " ")
        if self.is_image:
            name = name + self.ext
        return name

    def content(self):
        return file(self.fpath).read()

    @property
    def is_image(self):
        return self.ext in (".png", ".jpg", ".gif")

    @property
    def name(self):
        name = self.meta.get("name", "*** name not set ***")
        return name

    @property
    def sortkey(self):
        return self.meta.get("sortkey", "2")

    @property
    def size(self):
        "File size in KB"
        return utils.get_size(self.fpath)

    @property
    def skip_file(self):
        return self.size > utils.MAX_SIZE_KB

    def write(self, output_folder, text):
        loc = os.path.join(output_folder, self.fname)
        if op.abspath(loc) == op.abspath(self.fpath):
            raise Exception("may not overwrite the original file %s" % loc)

        d = os.path.dirname(loc)
        if not os.path.exists(d):
            os.makedirs(d)
        with open(loc, "wb") as fp:
            fp.write(text)

    def url(self, start=None):

        start = start or self

        rpath = op.relpath(self.root, start.dname)
        rpath = op.join(rpath, self.fname)

        return rpath, self.name


    def __repr__(self):
        return "File: %s (%s)" % (self.name, self.fname)

class PyGreen:
    TEMPLATE_DIR = op.abspath(op.join(op.split(__file__)[0], "templates"))

    def __init__(self):

        # the Bottle application
        self.app = bottle.Bottle()
        # a set of strings that identifies the extension of the files
        # that should be processed using Mako
        self.template_exts = set(["html"])
        # the folder where the files to serve are located. Do not set
        # directly, use set_folder instead
        self.folder = "."

        # recrawls directories on each request, use in serving
        self.refresh = True

        # the collection of files
        self.files = None

        # the TemplateLookup of Mako
        self.templates = TemplateLookup(directories=[self.folder, self.TEMPLATE_DIR],
                                        imports=["from markdown import markdown"],
                                        input_encoding='iso-8859-1',
                                        collection_size=100,
        )
        # A list of regular expression. Files whose the name match
        # one of those regular expressions will not be outputed when generating
        # a static version of the web site
        self.file_exclusion = [r".*\.mako", r".*\.py", r"(^|.*\/)\..*"]

        def is_public(path):
            for ex in self.file_exclusion:
                if re.match(ex, path):
                    return False
            return True

        def base_lister():
            files = []
            for dirpath, dirnames, filenames in os.walk(self.folder):
                filenames.sort()
                for f in filenames:
                    absp = os.path.join(dirpath, f)
                    path = os.path.relpath(absp, self.folder)
                    if is_public(path):
                        files.append(path)
            return files

            # A list of function. Each function must return a list of paths

        # of files to export during the generation of the static web site.
        # The default one simply returns all the files contained in the folder.
        # It is necessary to define new listers when new routes are defined
        # in the Bottle application, or the static site generation routine
        # will not be able to detect the files to export.
        self.file_listers = [base_lister]

        def file_renderer(path):
            if is_public(path):
                if path.split(".")[-1] in self.template_exts and self.templates.has_template(path):
                    f = File(fname=path, root=self.folder)
                    t = self.templates.get_template(path)
                    if self.refresh:
                        self.files = self.collect_files
                    data = t.render_unicode(p=self, f=f, u=utils)
                    return data.encode(t.module._source_encoding)
                return bottle.static_file(path, root=self.folder)
            return bottle.HTTPError(404, 'File does not exist.')

            # The default function used to render files. Could be modified to change the way files are

        # generated, like using another template language or transforming css...
        self.file_renderer = file_renderer
        self.app.route('/', method=['GET', 'POST', 'PUT', 'DELETE'])(lambda: self.file_renderer('index.html'))
        self.app.route('/<path:path>', method=['GET', 'POST', 'PUT', 'DELETE'])(lambda path: self.file_renderer(path))

    def set_folder(self, folder):
        """
        Sets the folder where the files to serve are located.
        """
        self.folder = folder
        self.templates.directories[0] = folder
        if self.folder not in sys.path:
            sys.path.append(self.folder)

        # append more ignored patterns
        ignore_file = op.join(self.folder, ".ignore")
        if os.path.isfile(ignore_file):
            patts = list(file(ignore_file))
            patts = map(lambda x: x.strip(), patts)
            patts = filter(lambda x: not x.startswith("#"), patts)
            self.file_exclusion.extend(patts)

    def run(self, host='0.0.0.0', port=8080):
        """
        Launch a development web server.
        """
        waitress.serve(self, host=host, port=port)

    def get(self, f):
        """
        Get the content of a file, indentified by its path relative to the folder configured
        in PyGreen. If the file extension is one of the extensions that should be processed
        through Mako, it will be processed.
        """
        handler = wsgiref.handlers.SimpleHandler(sys.stdin, sys.stdout, sys.stderr, {})
        handler.setup_environ()
        env = handler.environ
        env.update({'PATH_INFO': "/%s" % f.fname, 'REQUEST_METHOD': "GET"})
        out = b"".join(self.app(env, lambda *args: None))
        return out

    @property
    def settings(self):
        m = __import__('settings', globals(), locals(), [], -1)
        reload(m)
        return m

    def link(self, fname, start=None):

        items = filter(lambda x: re.search(fname, x.fname, re.IGNORECASE), self.files)
        if not items:
            f = self.files[0]
            _logger.error("*** name %s does not match" % fname)
        else:
            f = items[0]
            if len(items) > 1:
                _logger.warn("name %s matches more than one item" % fname)

        link, name = f.url(start)
        return '<a href="%s">%s</a>' % (link, name)

    def toc(self, tag=None, match=None, start=None):
        "Produces name, links pairs from file names"


        if tag:
            items = filter(lambda x: tag in x.meta['tags'], self.files)
        else:
            items = self.files

        if match:
            items = filter(lambda x: re.search(match, x.fname, re.IGNORECASE), self.files)

        if not items:
            _logger.error("*** tag %s does not match" % tag)

        urls = [f.url(start) for f in items]
        t = self.templates.get_template("toc.html")
        h = t.render_unicode(urls=urls)
        return h

    def gallery(self, match=None, start=None, span=4):
        "Produces name, links pairs from file names"

        items = filter(lambda x: x.is_image, self.files)

        if match:
            items = filter(lambda x: re.search(match, x.fname, re.IGNORECASE), self.files)

        urls = [ f.url(start) for f in items ]
        t = self.templates.get_template("gallery.html")
        h = t.render_unicode(urls=urls, span=span)
        return h

    @property
    def collect_files(self):
        """
        Collects all files that will be parsed. Will also be available in main context.
        TODO: this method crawls the entire directory tree each time it is accessed.
        It is handy during development but very large trees may affect performance.
        """
        files = []
        for l in self.file_listers:
            files += l()

        files = map(lambda x: File(x, self.folder), files)

        # apply sort order
        decor = [(f.sortkey, f.name, f) for f in files]
        decor.sort()
        return [ f[2] for f in decor ]

    def gen_static(self, output_folder):
        """
        Generates a complete static version of the web site. It will stored in 
        output_folder.
        """

        # this makes all files available in the template context
        self.files = self.collect_files
        self.files = filter(self.is_public, self.files)
        for f in self.files:
            if f.skip_file:
                _logger.info("skipping large file %s of %.1fkb" % (f.fname, f.size))
                continue
            _logger.info("generating %s" % f.fname)
            content = self.get(f)
            f.write(output_folder, content)

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)

    def cli(self, cmd_args=None):
        """
        The command line interface of PyGreen.
        """
        logging.basicConfig(level=logging.INFO, format='%(message)s')

        parser = argparse.ArgumentParser(description='PyBlue, micro web framework/static web site generator')
        subparsers = parser.add_subparsers(dest='action')

        parser_serve = subparsers.add_parser('serve', help='serve the web site')
        parser_serve.add_argument('-p', '--port', type=int, default=8080, help='folder containg files to serve')
        parser_serve.add_argument('-f', '--folder', default=".", help='folder containg files to serve')
        parser_serve.add_argument('-d', '--disable-templates', action='store_true', default=False,
                                  help='just serve static files, do not use invoke Mako')

        def serve():
            if args.disable_templates:
                self.template_exts = set([])
            self.run(port=args.port)

        parser_serve.set_defaults(func=serve)

        parser_gen = subparsers.add_parser('gen', help='generate a static version of the site')
        parser_gen.add_argument('output', help='folder to store the files')
        parser_gen.add_argument('-f', '--folder', default=".", help='folder containg files to serve')

        def gen():
            self.refresh = False
            self.gen_static(args.output)

        parser_gen.set_defaults(func=gen)

        args = parser.parse_args(cmd_args)
        self.set_folder(args.folder)
        print(parser.description)
        print("")
        args.func()


pygreen = PyGreen()

if __name__ == "__main__":
    pygreen.cli()
