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
        
    def __str__(self):
        return self.src + " -> " + self.dst

class Crawler(object):

    def __init__(self, root, depth_limit, confine=None, locked=True):
        self.root = root
        self.depth_limit = depth_limit
        self.locked = locked
        self.confine_prefix=confine
        self.host = urlparse.urlparse(root)[1]
        self.urls_seen = []
        self.links_seen = []
        self.links = 0
        self.num_followed = 0

        self.visited_links=[]

        self.url_filters=[self._prefix_ok,
                          self._not_visited,
                          self._same_host]

    def _prefix_ok(self, url):
        """Pass if the URL has the correct prefix, or none is specified"""
        return (self.confine_prefix is None  or
                url.startswith(self.confine_prefix))
    
    def _not_visited(self, url):
        """Pass if the URL has not already been visited"""
        return (url not in self.visited_links)
    
    def _same_host(self, url):
        """Pass if the URL is on the same host as the root URL"""
        try:
            host = urlparse.urlparse(url)[1]
            return re.match(".*%s" % self.host, host) 
        except Exception, e:
            print "ERROR: Can't process url '%s' (%s)" % (url, e)
            print format_exc()
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
            do_not_follow = [f for f in self.url_filters if not f(url)]
            
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
                    for link_url in page.out_links():
                        if link_url not in self.urls_seen:
                            self.links += 1
                            q.put((link_url, depth+1))
                            self.urls_seen.append(link_url)
                            self.links_seen.append(Link(url, link_url, "href"))
                except Exception, e:
                    print "ERROR: Can't process url '%s' (%s)" % (url, e)
                    print format_exc()

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

    parser.add_option("-L", "--show-links", action="store_true", default=False,
                      dest="out_links", help="Output links found")

    parser.add_option("-u", "--show-urls", action="store_true", default=False,
                      dest="out_urls", help="Output URLs found")


    opts, args = parser.parse_args()

    if len(args) < 1:
        parser.print_help(sys.stderr)
        raise SystemExit, 1

    if opts.out_links and opts.out_urls:
        parser.print_help(sys.stderr)
        parser.error("options -L and -u are mutually exclusive")

    return opts, args

def main():
    opts, args = parse_options()

    url = args[0]

    if opts.links:
        getLinks(url)
        raise SystemExit, 0

    depth_limit = opts.depth_limit
    confine_prefix=opts.confine

    sTime = time.time()

    print >> sys.stderr,  "Crawling %s (Max Depth: %d)" % (url, depth_limit)
    crawler = Crawler(url, depth_limit, confine_prefix)
    crawler.crawl()

    if opts.out_urls:
        print "\n".join(crawler.urls_seen)

    if opts.out_links:
        print "\n".join([str(l) for l in crawler.links_seen])

    eTime = time.time()
    tTime = eTime - sTime

    print >> sys.stderr, "Found:    %d" % crawler.links
    print >> sys.stderr, "Followed: %d" % crawler.num_followed
    print >> sys.stderr, "Stats:    (%d/s after %0.2fs)" % (
            int(math.ceil(float(crawler.links) / tTime)), tTime)

if __name__ == "__main__":
    main()
