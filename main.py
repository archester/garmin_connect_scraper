from urllib import urlencode
import urllib, urllib2, cookielib, json
import bs4
import re
import argparse
import os

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

def parseInputParams():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-u", "--user",
                        type=str,
                        help="Name of user to log to the garmin connect",
                        required=True)

    parser.add_argument("-p", "--password",
                        type=str,
                        help="Password to log to the garmin connect",
                        required=True)

    parser.add_argument("-n", "--num-activities",
                        type=int,
                        help="Scrap only the last X number of activities (0=all)",
                        default=0)

    parser.add_argument("--skip-gpx",
                        action="store_true",
                        help="Skip scraping the gpx files")

    parser.add_argument("--skip-details",
                        action="store_true",
                        help="Skip scraping activities details")

    parser.add_argument("--skip-splits",
                        action="store_true",
                        help="Skip scraping activities splits data")

    parser.add_argument("--input-file",
                        type=str,
                        help="Loads the activities from the existing json file given as a parameter. "
                               "Scraps only activities that do not exist in the given file.",
                        default="")

    parser.add_argument("--output-file",
                        type=str,
                        help="Save the scraped activities + activities from the input file to the "
                                "file given as a parameter.",
                        default="activities.json")

    return parser.parse_args()

class GarminActivitiesScraper():

    def __init__(self, skip_gpx=False, skip_details=False, skip_splits=False):
        # scraping options
        self._skip_gpx = skip_gpx
        self._skip_details = skip_details
        self._skip_splits = skip_splits
        # dictionary containing scraped activities data, activity_id is a key
        self._activities_data = {}

    def run(self, num_activities=0):
        num_scraped = 0
        for activities in self._get_activities_list():
            for activity_url in activities:
                activity_id = self._get_activity_id_from_url(activity_url)

                # check if it not already in our dict, if it's there skip it
                # that means that the activities were loaded from the file and we
                # are only appending new ones
                if activity_id in self._activities_data:
                    print("Skipping activity {}".format(activity_id))
                    continue

                activity_data = self._scrap_activity(activity_url)
                self._activities_data[activity_id] = activity_data
                num_scraped += 1
                if num_activities != 0 and num_scraped >= num_activities:
                    print("Done scraping activities.")
                    return

        print("Done scraping activities.")

    def save_to_json_file(self, out_file_name="activities.json"):
        with open(out_file_name, "w") as f:
            json.dump(self._activities_data, f, indent=3)

        return len(self._activities_data)

    def load_from_file(self, file_name):
        with open(file_name, "r") as f:
            self._activities_data = json.load(f)

        return len(self._activities_data)

    def get_scrapped_json_data(self):
        return self._activities_data

    """ PRIVATE """
    def _get_activities_list(self):
        activities = []
        while True:
            # get another page containing list of activities
            post_data = {} if len(activities) == 0 else self.NEXT_ACTIVITIES_POST_DATA
            res = http_req(self.URL_ACTIVITIES_LIST, post_data)

            # let's cook
            soup = bs4.BeautifulSoup(res, 'html.parser')

            # grab the activities
            next_activities = soup.findAll("a", { "class" : "activityNameLink" }, href=True)

            # TODO: is there a better way to check if we got to the end?
            if (next_activities == activities):
                print("Reached the end of activities")
                break

            activities = next_activities
            yield activities

    def _get_activity_id_from_url(self, activity_url):
        try:
            href = activity_url.get("href")
            return re.findall("\d+", href)[0]
        except ValueError:
            raise ValueError("Could not retrieve activity id from url: {} ".format(href))

    def _scrap_activity(self, activity_url):
        activity_data = {}
        activity_id = activity_data["id"] = self._get_activity_id_from_url(activity_url)
        activity_data["href"] = self.URL_ACTIVITY_PREFIX.format(activity_url["href"])

        # get main activity data
        name = self._scrap_activity_main_data(activity_id, activity_data)

        if not self._skip_splits:
            # get activity splits
            self._scrap_activity_splits_data(activity_id, activity_data)

        if not self._skip_details:
            # get activity details
            self._scrap_activity_details_data(activity_id, activity_data)

        if not self._skip_gpx:
            # download gpx file
            self._scrap_activity_gpx_data(activity_id, activity_data)

        print("Scraped activity {} - {}".format(len(self._activities_data) + 1, name.encode('utf-8')))

        return activity_data

    def _scrap_activity_main_data(self, activity_id, activity_data):
        activity_data["href-data-json"] = self.URL_ACTIVITY_DATA_JSON_PREFIX.format(activity_id)
        data_json = http_req(activity_data["href-data-json"])
        json_data = json.loads(data_json)
        name = json_data.get("activityName", "")
        activity_data["data"] = dict(json_data)

        return name

    def _scrap_activity_splits_data(self, activity_id, activity_data):
        activity_data["href-splits-json"] = self.URL_ACTIVITY_SPLITS_JSON_PREFIX.format(activity_id)
        splits_json = http_req(activity_data["href-splits-json"])
        json_data = json.loads(splits_json)
        activity_data["splits"] = dict(json_data)

    def _scrap_activity_details_data(self, activity_id, activity_data):
        activity_data["href-details-json"] = self.URL_ACTIVITY_DETAILS_JSON_PREFIX.format(activity_id)
        details_json = http_req(activity_data["href-details-json"])
        json_data = json.loads(details_json)
        activity_data["details"] = dict(json_data)

    def _scrap_activity_gpx_data(self, activity_id, activity_data):
        GPX_DIR = "gpx_output_files"
        if not os.path.exists(GPX_DIR):
            # TODO: avoid checking each time
            os.makedirs(GPX_DIR)

        try:
            activity_data["href-gpx-file"] = self.URL_ACTIVITY_GPX_FILE_PREFIX.format(activity_id)
            gpx_file_content = http_req(activity_data["href-gpx-file"])
        except Exception:
            # no gpx for this activity
            pass
        else:
            gpx_file_name = "{}{}activity_{}.gpx".format(GPX_DIR, os.path.sep, activity_id)
            with open(gpx_file_name, "w") as f:
                f.write(gpx_file_content)
            activity_data["local-gpx-file"] = gpx_file_name

    # ajax weirdness needed in POST data to force page containing next set of activities
    NEXT_ACTIVITIES_POST_DATA = {
       'AJAXREQUEST' : '_viewRoot',
       'activitiesForm' : 'activitiesForm',
       'javax.faces.ViewState' : 'j_id1',
       'ajaxSingle' : 'activitiesForm:pageScroller',
       'activitiesForm:pageScroller' : 'fastforward',
       'AJAX:EVENTS_COUNT' : '1',
    }

    URL_ACTIVITIES_LIST = "https://connect.garmin.com/minactivities"
    URL_ACTIVITY_PREFIX = "https://connect.garmin.com/modern/activity/{}"
    URL_ACTIVITY_DATA_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}"
    URL_ACTIVITY_SPLITS_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}/splits"
    URL_ACTIVITY_DETAILS_JSON_PREFIX = "https://connect.garmin.com/modern/proxy/activity-service/activity/{}/details"
    URL_ACTIVITY_GPX_FILE_PREFIX = "https://connect.garmin.com/modern/proxy/download-service/export/gpx/activity/{}"


def main():
    # read user parameters
    args = parseInputParams()

    # authenticate
    log_in(args)

    # set the stage
    scraper = GarminActivitiesScraper(skip_gpx=args.skip_gpx,
                                      skip_details=args.skip_details,
                                      skip_splits=args.skip_splits)
    if (args.input_file != ""):
        print("Loading activities from file {}...".format(args.input_file))
        activities_count = scraper.load_from_file(args.input_file)
        print("Loaded {} activities from file".format(activities_count))

    # scrap the data
    scraper.run(args.num_activities)

    # save to file
    print("Saving activities to file {}...".format(args.output_file))
    activities_count = scraper.save_to_json_file(args.output_file)
    print("Done. Saved {} activities.".format(activities_count))


if __name__ == "__main__": main()
