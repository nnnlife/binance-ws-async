from urllib.parse import urlencode


def cleanNoneValue(d) -> dict:
    out = {}
    for k in d.keys():
        if d[k] is not None:
            out[k] = d[k]
    return out


def encoded_string(query):
    return urlencode(query, True).replace("%40", "@")