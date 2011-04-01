#!/usr/bin/env python

"""Web Crawler/Spider

This module implements a web crawler. This is very _basic_ only
and needs to be extended to do anything usefull with the
traversed pages.

From: http://code.activestate.com/recipes/576551-simple-web-crawler/

"""

import re
import sys
import time
import math
import urllib2
import urlparse
import optparse
import hashlib
from cgi import escape
from traceback import format_exc
from Queue import Queue, Empty as QueueEmpty

from BeautifulSoup import BeautifulSoup

__version__ = "0.2"
__copyright__ = "CopyRight (C) 2008-2011 by James Mills"
__license__ = "MIT"
__author__ = "James Mills"
__author_email__ = "James Mills, James dot Mills st dotred dot com dot au"

USAGE = "%prog [options] <url>"
VERSION = "%prog v" + __version__

AGENT = "%s/%s" % (__name__, __version__)

class Link (object):

    def __init__(self, src, dst, link_type):
        self.src = src
        self.dst = dst
        self.link_type = link_type

    def __hash__(self):
        return hash((self.src, self.dst, self.link_type))

    def __eq__(self, other):
        return (self.src == other.src and
                self.dst == other.dst and
                self.link_type == other.link_type)
    
    def __str__(self):
        return self.src + " -> " + self.dst

class Crawler(object):

    def __init__(self, root, depth_limit, confine=None, exclude=[], locked=True, filter_seen=True):
        self.root = root
        self.depth_limit = depth_limit
        self.locked = locked
        self.confine_prefix=confine
        self.host = urlparse.urlparse(root)[1]
        self.urls_seen = []
        self.urls_remembered = []
        self.links_remembered = []
        self.links = 0
        self.num_followed = 0
        self.exclude_prefixes=exclude;

        self.visited_links=[]

        self.pre_visit_filters=[self._prefix_ok,
                                self._exclude_ok,
                                self._not_visited,
                                self._same_host]

        if filter_seen:
            self.post_visit_filters=[self._prefix_ok,
                                     self._same_host]
        else:
            self.post_visit_filters=[]

    def _pre_visit_url_condense(self, url):
        
        """Reduce URL in a flexible way.
        Discards queries and fragments
        """

        base, frag = urlparse.urldefrag(url)
        #u = urlparse.urlsplit(url)
        #newurl = urlparse.urlunsplit((u.scheme, u.netloc, u.path, "", ""))
        return base

    def _prefix_ok(self, url):
        """Pass if the URL has the correct prefix, or none is specified"""
        return (self.confine_prefix is None  or
                url.startswith(self.confine_prefix))

    def _exclude_ok(self, url):
        """Pass if the URL does not match any exclude patterns"""
        prefixes_ok = [ not url.startswith(p) for p in self.exclude_prefixes]
        print >> sys.stderr, url, prefixes_ok
        return all(prefixes_ok)
    
    def _not_visited(self, url):
        """Pass if the URL has not already been visited"""
        return (url not in self.visited_links)
    
    def _same_host(self, url):
        """Pass if the URL is on the same host as the root URL"""
        try:
            host = urlparse.urlparse(url)[1]
            return re.match(".*%s" % self.host, host) 
        except Exception, e:
            print >> sys.stderr, "ERROR: Can't process url '%s' (%s)" % (url, e)
            return False
            

    def crawl(self):
        
        q = Queue()
        q.put((self.root, 0))

        while not q.empty():
            url, depth = q.get()
            
            #Non-URL-specific filter: Discard anything over depth limit
            if depth > self.depth_limit:
                continue
            
            #Apply URL-based filters
            do_not_follow = [f for f in self.pre_visit_filters if not f(url)]
            
            #Special-case depth 0 (starting URL)
            if depth == 0 and [] != do_not_follow:
                print >> sys.stderr, "Whoops! Starting URL %s rejected by the following filters:", do_not_follow

            #If no filters failed (that is, all passed), process URL
            if [] == do_not_follow:
                try:
                    self.visited_links.append(url)
                    self.num_followed += 1
                    page = Fetcher(url)
                    page.fetch()
                    for link_url in [self._pre_visit_url_condense(l) for l in page.out_links()]:
                        if link_url not in self.urls_seen:
                            q.put((link_url, depth+1))
                            self.urls_seen.append(link_url)
                            
                        do_not_remember = [f for f in self.post_visit_filters if not f(link_url)]
                        if [] == do_not_remember:
                                self.links += 1
                                self.urls_remembered.append(link_url)
                                link = Link(url, link_url, "href")
                                if link not in self.links_remembered:
                                    self.links_remembered.append(link)
                except Exception, e:
                    print >>sys.stderr, "ERROR: Can't process url '%s' (%s)" % (url, e)
                    #print format_exc()

class OpaqueDataException (Exception):
    def __init__(self, message, mimetype, url):
        Exception.__init__(self, message)
        self.mimetype=mimetype
        self.url=url
        

class Fetcher(object):
    
    """The name Fetcher is a slight misnomer: This class retrieves and interprets web pages."""

    def __init__(self, url):
        self.url = url
        self.out_urls = []

    def __getitem__(self, x):
        return self.out_urls[x]

    def out_links(self):
        return self.out_urls

    def _addHeaders(self, request):
        request.add_header("User-Agent", AGENT)

    def _open(self):
        url = self.url
        try:
            request = urllib2.Request(url)
            handle = urllib2.build_opener()
        except IOError:
            return None
        return (request, handle)

    def fetch(self):
        request, handle = self._open()
        self._addHeaders(request)
        if handle:
            try:
                data=handle.open(request)
                mime_type=data.info().gettype()
                url=data.geturl();
                if mime_type != "text/html":
                    raise OpaqueDataException("Not interested in files of type %s" % mime_type,
                                              mime_type, url)
                content = unicode(data.read(), "utf-8",
                        errors="replace")
                soup = BeautifulSoup(content)
                tags = soup('a')
            except urllib2.HTTPError, error:
                if error.code == 404:
                    print >> sys.stderr, "ERROR: %s -> %s" % (error, error.url)
                else:
                    print >> sys.stderr, "ERROR: %s" % error
                tags = []
            except urllib2.URLError, error:
                print >> sys.stderr, "ERROR: %s" % error
                tags = []
            except OpaqueDataException, error:
                print >>sys.stderr, "Skipping %s, has type %s" % (error.url, error.mimetype)
                tags = []
            for tag in tags:
                href = tag.get("href")
                if href is not None:
                    url = urlparse.urljoin(self.url, escape(href))
                    if url not in self:
                        self.out_urls.append(url)

def getLinks(url):
    page = Fetcher(url)
    page.fetch()
    for i, url in enumerate(page):
        print "%d. %s" % (i, url)

def parse_options():
    """parse_options() -> opts, args

    Parse any command-line options given returning both
    the parsed options and arguments.
    """

    parser = optparse.OptionParser(usage=USAGE, version=VERSION)

    parser.add_option("-q", "--quiet",
            action="store_true", default=False, dest="quiet",
            help="Enable quiet mode")

    parser.add_option("-l", "--links",
            action="store_true", default=False, dest="links",
            help="Get links for specified url only")    

    parser.add_option("-d", "--depth",
            action="store", type="int", default=30, dest="depth_limit",
            help="Maximum depth to traverse")

    parser.add_option("-c", "--confine",
            action="store", type="string", dest="confine",
            help="Confine crawl to specified prefix")

    parser.add_option("-x", "--exclude", action="append", type="string",
                      dest="exclude", default=[], help="Exclude URLs by prefix")
    
    parser.add_option("-L", "--show-links", action="store_true", default=False,
                      dest="out_links", help="Output links found")

    parser.add_option("-u", "--show-urls", action="store_true", default=False,
                      dest="out_urls", help="Output URLs found")

    parser.add_option("-D", "--dot", action="store_true", default=False,
                      dest="out_dot", help="Output Graphviz dot file")
    


    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.print_help(sys.stderr)
        raise SystemExit, 1

    if opts.out_links and opts.out_urls:
        parser.print_help(sys.stderr)
        parser.error("options -L and -u are mutually exclusive")

    return opts, args

def dot_safe_alias(url):
    
    """ Make some unique string which DOT can live with"""

    m = hashlib.md5()
    m.update(url)
    return "N"+m.hexdigest()

def main():    
    opts, args = parse_options()

    url = args[0]

    if opts.links:
        getLinks(url)
        raise SystemExit, 0

    depth_limit = opts.depth_limit
    confine_prefix=opts.confine
    exclude=opts.exclude

    sTime = time.time()

    print >> sys.stderr,  "Crawling %s (Max Depth: %d)" % (url, depth_limit)
    crawler = Crawler(url, depth_limit, confine_prefix, exclude)
    crawler.crawl()

    if opts.out_urls:
        print "\n".join(crawler.urls_seen)

    if opts.out_links:
        print "\n".join([str(l) for l in crawler.links_remembered])
        
    if opts.out_dot:
        node_alias = {}
        print "digraph Crawl {"
        print "\t edge [K=0.2, len=0.1];"
        for l in crawler.links_remembered:            
            if l.src not in node_alias:
                node_alias[l.src] = dot_safe_alias(l.src)
                print "\t%s [label=\"%s\"];" % (node_alias[l.src], l.src)
            if l.dst not in node_alias:
                node_alias[l.dst] = dot_safe_alias(l.dst)
                print "\t%s [label=\"%s\"];" % (node_alias[l.dst], l.dst)
            print "\t" + node_alias[l.src] + " -> " + node_alias[l.dst] + ";"
        print  "}"

    eTime = time.time()
    tTime = eTime - sTime

    print >> sys.stderr, "Found:    %d" % crawler.links
    print >> sys.stderr, "Followed: %d" % crawler.num_followed
    print >> sys.stderr, "Stats:    (%d/s after %0.2fs)" % (
            int(math.ceil(float(crawler.links) / tTime)), tTime)

if __name__ == "__main__":
    main()
