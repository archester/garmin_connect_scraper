"""
The MIT License (MIT)

Copyright (c) 2015 Kyle Krafka

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

"""
The code in this file is a great effort from Kyle Krafka's project:
https://github.com/kjkjava/garmin-connect-export
I copied his code and slightly modified to fit my needs. 
"""

from urllib import urlencode
import urllib, urllib2, cookielib, json

cookie_jar = cookielib.CookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))

# url is a string, post is a dictionary of POST parameters
def http_req(url, post=None):
    request = urllib2.Request(url)
    request.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/54.0.2816.0 Safari/537.36')  # Tell Garmin we're some supported browser.

    if post:
        post = urlencode(post)  # Convert dictionary to POST parameter string.

    response = opener.open(request, data=post)  # This line may throw a urllib2.HTTPError.

    if response.getcode() != 200:
        raise Exception('Bad return code (' + str(response.getcode()) + ') for: ' + url)

    return response.read()

def log_in(args):

    REDIRECT = "https://connect.garmin.com/post-auth/login"
    BASE_URL = "http://connect.garmin.com/en-US/signin"
    GAUTH = "http://connect.garmin.com/gauth/hostname"
    SSO = "https://sso.garmin.com/sso"
    CSS = "https://static.garmincdn.com/com.garmin.connect/ui/css/gauth-custom-v1.1-min.css"

    hostname_url = http_req(GAUTH)
    hostname = json.loads(hostname_url)['host']

    data = {'service': REDIRECT,
        'webhost': hostname,
        'source': BASE_URL,
        'redirectAfterAccountLoginUrl': REDIRECT,
        'redirectAfterAccountCreationUrl': REDIRECT,
        'gauthHost': SSO,
        'locale': 'en_US',
        'id': 'gauth-widget',
        'cssUrl': CSS,
        'clientId': 'GarminConnect',
        'rememberMeShown': 'true',
        'rememberMeChecked': 'false',
        'createAccountShown': 'true',
        'openCreateAccount': 'false',
        'usernameShown': 'false',
        'displayNameShown': 'false',
        'consumeServiceTicket': 'false',
        'initialFocus': 'true',
        'embedWidget': 'false',
        'generateExtraServiceTicket': 'false'}

    # URLs for various services.
    url_gc_login = 'https://sso.garmin.com/sso/login?' + urllib.urlencode(data)
    url_gc_post_auth = 'https://connect.garmin.com/post-auth/login?'

    print("Authenticating...")
    # Initially, we need to get a valid session cookie, so we pull the login page.
    http_req(url_gc_login)
    # Now we'll actually login.
    post_data = {'username': args.user, 'password': args.password, 'embed': 'true', 'lt': 'e1s1', '_eventId': 'submit', 'displayNameRequired': 'false'}  # Fields that are passed in a typical Garmin login.
    http_req(url_gc_login, post_data)

    try:
        login_ticket = [cookie.value for cookie in cookie_jar if cookie.name == "CASTGC"][0]
    except ValueError:
        raise Exception("Did not get a ticket cookie. Cannot log in. Did you enter the correct username and password?")

    # Chop of 'TGT-' off the beginning, prepend 'ST-0'.
    login_ticket = 'ST-0' + login_ticket[4:]
    http_req(url_gc_post_auth + 'ticket=' + login_ticket)
    print("Success")
