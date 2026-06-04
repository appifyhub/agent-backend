from urllib.parse import parse_qs, urlencode, urlparse

# it's not perfect but it's a start
WEB_SUBDOMAINS = ["www", "www1", "www2", "w3", "web", "www-s1"]
TRACKING_PARAMS = [
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_name", "utm_id",
    "utm_reader", "utm_place", "utm_pubreferrer", "utm_swu", "utm_viz_id", "utm_referrer",
    "utm_source_referrer", "utm_source_ref", "utm_source_referral", "utm_source_referral",
    "fb_action_ids", "fb_action_types", "fb_ref", "fb_source",
    "action_object_map", "action_type_map", "action_ref_map", "action_ids", "action_types",
    "action_source", "action_object", "action_ref", "action_click", "action", "ref_component",
    "gclid", "fbclid", "s", "sid", "si", "igshid", "sessionid", "session_id",
    "shareId", "share_id", "shareid", "ref", "ref_src", "hl",
    "PHPSESSID", "JSESSIONID", "ASP.NET_SessionId", "ASPSESSIONID",
    "token", "access_token", "auth_token", "oauth_token", "oauth_verifier",
]


def simplify_url(url: str, strip_subdomains: bool = True) -> str:
    # split into domain part and query+fragment part for cleanup
    url_parts = url.split("?")
    parsed_url = urlparse(url_parts[0])
    if strip_subdomains:
        domain = ".".join(
            [part for part in parsed_url.netloc.split(".") if part not in WEB_SUBDOMAINS],
        )
        simple_url = f"{domain}{parsed_url.path or ''}"
    else:
        simple_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path or ''}"
    # remove tracking parameters from the query string
    query_string = url_parts[1] if len(url_parts) > 1 else ""
    query_map = {
        param: first_value
        for param, first_value in {
            key: all_values[0]
            # parse the query string and filter to take only the first value of each parameter
            for key, all_values in parse_qs(query_string).items()
        }.items()
        if param not in TRACKING_PARAMS
    }
    # join the simple URL and the cleaned query string (implicitly removing empty params and fragments)
    query_string = urlencode(query_map)
    return f"{simple_url}{'?' + query_string if query_string else ''}"
