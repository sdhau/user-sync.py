import collections
import time
from random import randint
from six.moves import urllib
import hmac
import base64
import hashlib
import requests
import re
import json


class OnerosterAPI:
    """ Starts connection and makes queries with One-Roster API"""

    def __init__(self, logger, options):
        self.logger = logger
        self.host_name = options['host']
        self.limit = options['limit']
        self.client_id = options['client_id']
        self.client_secret = options['client_secret']
        self.oneroster = OneRoster(self.client_id, self.client_secret)
        self.key_identifier = options['key_identifier']

    def get_users(self, group_filter, group_name, user_filter, finder_option):
        list_api_results = []
        if group_filter == 'courses':
            key_id = self.execute_actions('courses', group_name, self.key_identifier, 'key_identifier')
            if key_id.__len__() == 0:
                return list_api_results
            list_classes = self.execute_actions(group_filter, user_filter, key_id, 'course_classlist')
            for each_class in list_classes:
                list_api_results.extend(self.execute_actions('classes', user_filter, each_class, 'mapped_users'))
        elif finder_option == 'all_users':
            list_api_results.extend(self.execute_actions(None, user_filter, None, 'all_users'))
        else:
            key_id = self.execute_actions(group_filter, None, group_name, 'key_identifier')
            if key_id.__len__() == 0:
                return list_api_results
            list_api_results.extend(self.execute_actions(group_filter, user_filter, key_id, 'mapped_users'))
        return list_api_results

    def construct_url(self, base_string_seeking, id_specified, finder_option, users_filter):
        if finder_option == 'course_classlist':
            url_ender = 'courses/?limit=' + self.limit + '&offset=0'
        elif finder_option == 'users_from_course':
            url_ender = 'courses/' + id_specified + '/classes?limit=' + self.limit + '&offset=0'
        elif users_filter is not None:
            url_ender = base_string_seeking + '/' + id_specified + '/' + users_filter + '?limit=' + self.limit + '&offset=0'
        else:
            url_ender = base_string_seeking + '?limit=' + self.limit + '&offset=0'
        return self.host_name + url_ender

    def execute_actions(self, group_filter, user_filter, identifier, finder_option):
        result = []
        if finder_option == 'all_users':
            url_request = self.construct_url(user_filter, None, '', None)
            result = self.make_call(url_request, 'all_users', None)
        elif finder_option == 'key_identifier':
            if group_filter == 'courses':
                url_request = self.construct_url(user_filter, identifier, 'course_classlist', None)
                result = self.make_call(url_request, 'key_identifier', group_filter, user_filter)
            else:
                url_request = self.construct_url(group_filter, identifier, 'key_identifier', None)
                result = self.make_call(url_request, 'key_identifier', group_filter, identifier)
        elif finder_option == 'mapped_users':
            base_filter = group_filter if group_filter == 'schools' else 'classes'
            url_request = self.construct_url(base_filter, identifier, finder_option, user_filter)
            result = self.make_call(url_request, 'mapped_users', group_filter, group_filter)
        elif finder_option == 'course_classlist':
            url_request = self.construct_url("", identifier, 'users_from_course', None)
            result = self.make_call(url_request, finder_option, group_filter)

        return result

    def make_call(self, url_request, finder_option, group_filter, group_name=None):
        list_api_results = []
        key = 'first'
        while key is not None:
            response = self.oneroster.make_roster_request(url_request) \
                if key == 'first' \
                else self.oneroster.make_roster_request(response.links[key]['url'])
            if response.ok is not True:
                status = response.status_code
                message = response.reason
                raise ValueError('Non Successful Response'
                                 + '  ' + 'status:' + str(status) + '  ' + 'message:' + str(message))
            if finder_option == 'key_identifier':
                other = 'course' if group_filter == 'courses' else 'classes'
                name_identifier, revised_key = ('name', 'orgs') if group_filter == 'schools' else ('title', other)
                for each_class in json.loads(response.content).get(revised_key):
                    if self.encode_str(each_class[name_identifier]) == self.encode_str(group_name):
                        try:
                            key_id = each_class[self.key_identifier]
                        except ValueError:
                            raise ValueError('Key identifier: ' + self.key_identifier + ' not a valid identifier')
                        list_api_results.append(key_id)
                        return list_api_results[0]

            elif finder_option == 'course_classlist':
                for ignore, each_class in json.loads(response.content).items():
                    list_api_results.append(each_class[0][self.key_identifier])

            else:
                for ignore, users in json.loads(response.content).items():
                    list_api_results.extend(users)
            if key == 'last' or int(response.headers._store['x-count'][1]) < int(self.limit):
                break
            key = 'next' if 'next' in response.links else 'last'

        if list_api_results.__len__() == 0:
            self.logger.warning("No " + finder_option + " for " + group_filter + "  " + group_name)

        return list_api_results

    def encode_str(self, text):
        return re.sub(r'(\s)', '', text).lower()


class OneRoster(object):
    def __init__(self, client_id, client_secret):
        self._client_id = client_id
        self._client_secret = client_secret

    def make_roster_request(self, url):

        """
        make a request to a given url with the stored key and secret
        :param url:     The url for the request
        :return:        A dictionary containing the status_code and response
        """

        # Generate timestamp and nonce
        timestamp = str(int(time.time()))
        nonce = self.__generate_nonce(len(timestamp))

        # Define oauth params
        oauth = {
            'oauth_consumer_key': self._client_id,
            'oauth_signature_method': 'HMAC-SHA256',
            'oauth_timestamp': timestamp,
            'oauth_nonce': nonce
        }

        # Split the url into base url and params
        url_pieces = url.split("?")

        url_params = {}

        # Add the url params if they exist
        if len(url_pieces) == 2:
            url_params = self.__paramsToDict(url_pieces[1])
            all_params = self.__merge_dicts(oauth, url_params)
        else:
            all_params = oauth.copy()

        # Generate the auth signature
        base_info = self.__build_base_string(url_pieces[0], 'GET', all_params)
        composite_key = urllib.parse.quote_plus(self._client_secret) + "&"
        auth_signature = self.__generate_auth_signature(base_info, composite_key)
        oauth["oauth_signature"] = auth_signature

        # Generate the auth header
        auth_header = self.__build_auth_header(oauth)

        return self.__make_get_request(url_pieces[0], auth_header, url_params)

    def __merge_dicts(self, oauth, params):
        """
        Merge the oauth and param dictionaries
        :param oauth:       The oauth params
        :param params:      The url params
        :return:            A merged dictionary
        """
        result = oauth.copy()
        result.update(params)
        return result

    def __generate_nonce(self, nonce_len):
        """
        Generate a random nonce
        :param nonce_len:   Length of the nonce
        :return:            The nonce
        """
        characters = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        result = ""
        for i in range(0, nonce_len):
            result += characters[randint(0, len(characters) - 1)]

        return result

    def __paramsToDict(self, url_params):
        """
        Convert the url params to a dict
        :param url_params:      The url params
        :return:                A dictionary of the url params
        """
        params = url_params.split("&")
        result = {}
        for value in params:
            value = urllib.parse.unquote(value)
            split = value.split("=")
            if len(split) == 2:
                result[split[0]] = split[1]
            else:
                result["filter"] = value[7:]
        return result

    def __build_base_string(self, baseurl, method, all_params):
        """
        Generate the base string for the generation of the oauth signature
        :param baseurl:     The base url
        :param method:      The HTTP method
        :param all_params:  The url and oauth params
        :return:            The base string for the generation of the oauth signature
        """
        result = []
        params = collections.OrderedDict(sorted(all_params.items()))
        for key, value in params.items():
            result.append(key + "=" + urllib.parse.quote(value))
        return method + "&" + urllib.parse.quote_plus(baseurl) + "&" + urllib.parse.quote_plus("&".join(result))

    def __generate_auth_signature(self, base_info, composite_key):
        """
        Generate the oauth signature
        :param base_info:       The base string generated from method, url, and params
        :param composite_key:   The componsite key of secret and &
        :return:                The oauth signature
        """
        digest = hmac.new(str.encode(composite_key), msg=str.encode(base_info), digestmod=hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def __build_auth_header(self, oauth):
        """
        Generates the oauth header from the oauth params
        :param oauth:   The oauth params
        :return:        The oauth header for the request
        """
        result = "OAuth "
        values = []
        for key, value in oauth.items():
            values.append(key + "=\"" + urllib.parse.quote_plus(value) + "\"")

        result += ",".join(values)
        return result

    def __make_get_request(self, url, auth_header, url_params):
        """
        Make the get request
        :param url:             The base url of the request
        :param auth_header:     The auth header
        :param url_params:      The params from the url
        :return:                A dictionary of the status_code and response
        """

        try:
            return requests.get(url=url, headers={"Authorization": auth_header}, params=url_params)

        except Exception as e:
            return {"status_code": 0, "response": "An error occurred, check your URL"}
