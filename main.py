from urllib import urlencode
import urllib, urllib2, cookielib, json
import bs4
import re
import argparse
 
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
    url_gc_login     = 'https://sso.garmin.com/sso/login?' + urllib.urlencode(data)
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
    print("Finished authentication")

def parseInputParams():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-u", "--user",
                        type = str,
                        help = "Name of user to log to the garmin connect",
                        required = True)
    
    parser.add_argument("-p", "--password",
                        type = str,
                        help = "Password to log to the garmin connect",
                        required = True)

    return parser.parse_args()

class GarminActivitiesScraper():
    # ajax weirdness needed in POST data to force page containing next set of activities
    NEXT_ACTIVITIES_POST_DATA = {
       'AJAXREQUEST' : '_viewRoot',
       'activitiesForm' : 'activitiesForm',
       'javax.faces.ViewState' : 'j_id1',
       'ajaxSingle' : 'activitiesForm:pageScroller',
       'activitiesForm:pageScroller' : 'fastforward',
       'AJAX:EVENTS_COUNT' : '1',
    }
    
    URL_ACTIVITY_PREFIX = "https://connect.garmin.com/modern/activity/{}"
    URL_ACTIVITY_DATA_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}"
    URL_ACTIVITY_SPLITS_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}/splits"
    URL_ACTIVITY_DETAILS_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}/details"
    URL_ACTIVITY_GPX_FILE_PREFIX = "https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/{}"
    
    def run(self):    
        i = 1
        activities = []
        activities_data = {} 
        while True:
            # get another page containing list of activities
            post_data = {} if i <= 1 else self.NEXT_ACTIVITIES_POST_DATA
            res = http_req("https://connect.garmin.com/minactivities", post_data)
        
            # let's cook
            soup = bs4.BeautifulSoup(res, 'html.parser')
        
            # grab the activities 
            next_activities = soup.findAll("a", { "class" : "activityNameLink" }, href = True)
            
            # TODO: is there a better way to check if we got to the end?
            if (next_activities == activities):
                print("Reached the end of activities")
                break
        
            activities = next_activities
            print("Scraping {} activities from set {}".format(len(activities), i))
            
            for j, activity in enumerate(activities):
                activity_data = {}        
                idx = activity_data["id"] = re.findall("\d+", activity["href"])[0] # TODO: try
                activity_data["href"] = self.URL_ACTIVITY_PREFIX.format(activity["href"])         
                
                # get activity data
                activity_data["href-data-json"] = self.URL_ACTIVITY_DATA_JSON_PREFIX.format(idx)
                data_json = http_req(activity_data["href-data-json"])
                json_data = json.loads(data_json)
                name = json_data.get("activityName", "")                
                activity_data["data"] = dict(json_data)
                
                # get activity splits
                activity_data["href-splits-json"] = self.URL_ACTIVITY_SPLITS_JSON_PREFIX.format(idx)
                splits_json = http_req(activity_data["href-splits-json"])
                json_data = json.loads(splits_json)
                activity_data["splits"] = dict(json_data)
                
                # get activity details
                activity_data["href-details-json"] = self.URL_ACTIVITY_DETAILS_JSON_PREFIX.format(idx)
                details_json = http_req(activity_data["href-details-json"])
                json_data = json.loads(details_json)
                activity_data["details"] = dict(json_data)
        
                # download gpx file
                try:
                    activity_data["href-gpx-file"] = self.URL_ACTIVITY_GPX_FILE_PREFIX.format(idx)
                    gpx_file_content = http_req(activity_data["href-gpx-file"])
                except Exception:
                    # no gpx for this activity
                    pass
                else:
                    gpx_file = "gpx/activity_{}.gpx".format(idx)
                    with open(gpx_file, "w") as f:
                        f.write(gpx_file_content)
                    activity_data["local-gpx-file"] = gpx_file
                              
                activities_data[idx] = activity_data
                print("Scrapped activity {} - {}".format(i, name.encode('utf-8')))
#                 break
#             break
            i += 1
            
        # print("activities_data", activities_data)
        with open("activities.json", "w") as f:
            json.dump(activities_data, f, indent = 3)
        
        print("Done.")

def main():
    # read user parameters
    args = parseInputParams()
    
    # authenticate
    log_in(args)
    
    # scrap the data    
    scraper = GarminActivitiesScraper()
    scraper.run()


if __name__ == "__main__": main()