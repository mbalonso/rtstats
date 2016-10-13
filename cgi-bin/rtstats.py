#!/usr/bin/env python
"""I should answer the following URIs

    .../siteindex
    .../iddstats_nc?EXP+server1.smn.gov.ar
    .../iddbinstats_nc?EXP+server1.smn.gov.ar  [latency histogram]
    .../iddstats_vol_nc?EXP+server1.smn.gov.ar [volume]
    .../iddstats_num_nc?HDS+server1.smn.gov.ar [products]
    .../iddstats_topo_nc?HDS+metfs1.agron.iastate.edu [topology]
    .../rtstats_summary_volume?metfs1.agron.iastate.edu [text stats]
"""
import os
import sys
import requests
import numpy as np
import re
import pandas as pd
import myview
RE_IP = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')


def get_domain(val):
    """Convert whatever this is, into a domain

    1.2.3.4 becomes 1.2.3
    mesonet.agron.iastate.edu becomes edu.iastate.agron
    blah becomes ''
    """
    if val.find(".") == -1:
        return ''
    if RE_IP.match(val):
        return val.rsplit(".", 1)[0]
    return ".".join(val.split(".")[1:][::-1])


def handle_site(hostname):
    sys.stdout.write("Content-type: text/html\n\n")
    req = requests.get(("http://rtstats.local/services/host/%s/feedtypes.json"
                        ) % (hostname, ))
    if req.status_code != 200:
        sys.stdout.write("API Service Failure...")
        return
    j = req.json()
    sys.stdout.write(("<table border=\"1\" cellpadding=\"2\" cellspacing=\"0\""
                      "><thead><tr><th>Feed Name</th>"
                      "<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
                      "<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
                      "</tr></thead>"))
    for feedtype in j['feedtypes']:
        sys.stdout.write(("<tr><th>%s</th>") % (feedtype,))
        sys.stdout.write("""
<td><a href="%(p)s/iddstats_nc?%(f)s+%(h)s">latency</a></td>
<td><a href="%(p)s/iddstats_nc?%(f)s+%(h)s+LOG">log(latency)</a></td>
<td><a href="%(p)s/iddbinstats_nc?%(f)s+%(h)s">histogram</a></td>
<td><a href="%(p)s/iddstats_vol_nc?%(f)s+%(h)s">volume</a></td>
<td><a href="%(p)s/iddstats_num_nc?%(f)s+%(h)s">products</a></td>
<td><a href="%(p)s/iddstats_topo_nc?%(f)s+%(h)s">topology</a></td>
        """ % dict(h=hostname, f=feedtype, p="/cgi-bin/rtstats"))
        sys.stdout.write("</tr>")
    sys.stdout.write("</table>")

    sys.stdout.write("""<p>
<a href="%(p)s?%(h)s">Cumulative volume summary</a>
<a href="%(p)s?%(h)s+GRAPH">Cumulative volume summary praph</a>
    """ % dict(h=hostname, p="/cgi-bin/rtstats/rtstats_summary_volume"))


def handle_siteindex():
    sys.stdout.write("Content-type: text/html\n\n")
    req = requests.get("http://rtstats.local/services/hosts.geojson")
    if req.status_code != 200:
        sys.stdout.write("API Service Failure...")
        return
    j = req.json()
    domains = dict()
    for feature in j['features']:
        host = feature['properties']['hostname']
        ldmversion = feature['properties']['ldmversion']
        d = get_domain(host)
        d2 = domains.setdefault(d, dict())
        d2[host] = ldmversion

    content = ("<table border=\"1\" cellpadding=\"2\" cellspacing=\"0\""
               "><thead><tr><th>Domain</th>"
               "<th>Hosts</th></tr></thead>")
    keys = domains.keys()
    keys.sort()
    for d in keys:
        domain = domains[d]
        dkeys = domain.keys()
        dkeys.sort()
        content += ("<tr><th>%s</th><td>") % (d,)
        for h in dkeys:
            content += ("<a href=\"/cgi-bin/rtstats/siteindex?%s\">"
                        "%s</a> [%s]<br />"
                        ) % (h, h, domain[h])
        content += "</td></tr>"
    content += "</table>"
    view = myview.MyView()
    view.vars['content'] = content
    sys.stdout.write(view.render('main.html'))


def handle_volume_stats_plot(hostname):
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    req = requests.get(("http://rtstats.local/services/host/%s/"
                        "hourly.json"
                        ) % (hostname, ))
    if req.status_code != 200:
        sys.stdout.write("API Service Failure...")
        return
    j = req.json()
    df = pd.DataFrame(j['data'], columns=j['columns'])
    df['nbytes'] /= (1024 * 1024)
    df['valid'] = pd.to_datetime(df['valid'])
    _ = plt.figure(figsize=(11, 7))
    ax = plt.axes([0.1, 0.1, 0.6, 0.8])
    gdf = df[['valid', 'feedtype', 'nbytes']].groupby(['valid', 'feedtype']
                                                      ).sum()
    gdf.reset_index(inplace=True)
    pdf = gdf.pivot('valid', 'feedtype', 'nbytes')
    floor = np.zeros(len(pdf.index))
    colors = plt.get_cmap('rainbow')(np.linspace(0, 1, len(pdf.columns)))
    for i, feedtype in enumerate(pdf.columns):
        ax.bar(pdf.index.values, pdf[feedtype].values, width=1/24.,
               bottom=floor, fc=colors[i], label=feedtype, align='center')
        floor += pdf[feedtype].values

    ax.legend(bbox_to_anchor=(1.01, 1), loc=2, borderaxespad=0.,
              fontsize=12)
    ax.set_title(("%s\n%s to %s UTC"
                  ) % (hostname,
                       df['valid'].min().strftime("%Y%m%d/%H%M"),
                       df['valid'].max().strftime("%Y%m%d/%H%M")))
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hz\n%-d %b"))
    ax.set_ylabel("Data Volume [MiB]")
    sys.stdout.write("Content-type: image/png\n\n")
    plt.savefig(sys.stdout)


def handle_volume_stats(hostname):
    sys.stdout.write("Content-type: text/html\n\n")
    req = requests.get(("http://rtstats.local/services/host/%s/"
                        "hourly.json"
                        ) % (hostname, ))
    if req.status_code != 200:
        sys.stdout.write("API Service Failure...")
        return
    j = req.json()
    df = pd.DataFrame(j['data'], columns=j['columns'])
    df['valid'] = pd.to_datetime(df['valid'])
    maxbytes = df[['valid', 'nbytes']].groupby('valid').sum().max()['nbytes']
    avgbytes = df[['valid', 'nbytes']].groupby('valid').sum().mean()['nbytes']
    avgprods = df[['valid', 'nprods']].groupby('valid').sum().mean()['nprods']
    feedtypetots = df.groupby('feedtype').sum()['nbytes'].sort_values(
        ascending=False)
    total = float(feedtypetots.sum())
    listing = ""
    for feedtype, nbytes in feedtypetots.iteritems():
        fdf = df[df['feedtype'] == feedtype]
        avgbyteshr = fdf[['valid', 'nbytes']].groupby('valid').sum(
            ).mean()['nbytes']
        maxbyteshr = fdf[['valid', 'nbytes']].groupby('valid').sum(
            ).max()['nbytes']
        avgprodshr = fdf[['valid', 'nprods']].groupby('valid').sum(
            ).mean()['nprods']
        listing += ("%-18s %12.3f    [%7.3f%%] %12.3f %12.3f\n"
                    ) % (feedtype, avgbyteshr / 1000000.,
                         nbytes / total * 100.,
                         maxbyteshr / 1000000., avgprodshr)
    content = """<pre>
    Data Volume Summary for %s

Maximum hourly volume  %10.3f M bytes/hour
Average hourly volume  %10.3f M bytes/hour

Average products per hour  %10.0f prods/hour

Feed                           Average             Maximum     Products
                     (M byte/hour)            (M byte/hour)   number/hour
%s
</pre>
""" % (hostname, maxbytes / 1000000., avgbytes / 1000000., avgprods, listing)
    view = myview.MyView()
    view.vars['content'] = content
    sys.stdout.write(view.render('main.html'))


def handle_topology(hostname, feedtype):
    sys.stdout.write("Content-type: text/html\n\n")
    req = requests.get(("http://rtstats.local/services/host/%s/"
                        "topology.json?feedtype=%s"
                        ) % (hostname, feedtype))
    if req.status_code != 200:
        sys.stdout.write("API Service Failure...")
        return
    j = req.json()
    routes = {}
    if isinstance(j, unicode):
        view = myview.MyView()
        view.vars['content'] = "No topology found for host"
        sys.stdout.write(view.render('main.html'))
        return
    for path in j['paths']:
        routes[",".join(path)] = path[-1]
    content = "<br />%s\n" % (hostname,)
    keys = routes.keys()
    keys.sort()
    for key in keys:
        content += "<br />"
        content += "&nbsp;&nbsp;&nbsp;&nbsp;" * (len(key.split(",")) - 1)
        content += ("<a href=\"iddstats_topo_nc?%s+%s\">%s</a>\n"
                    ) % (feedtype, routes[key], routes[key])
    view = myview.MyView()
    view.vars['content'] = content
    sys.stdout.write(view.render('main.html'))


def plot_latency(feedtype, host, logopt):
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    req = requests.get(("http://rtstats.local/services/host/%s/rtstats.json"
                        ) % (host, ))
    if req.status_code != 200:
        sys.stdout.write("Content-type: text/plain\n\n")
        sys.stdout.write("API Service Failure...")
        return

    j = req.json()
    df = pd.DataFrame(j['data'], columns=j['columns'])
    df = df[df['feedtype'] == feedtype]
    df['entry_added'] = pd.to_datetime(df['entry_added'])
    _ = plt.figure(figsize=(11, 7))
    ax = plt.axes([0.1, 0.1, 0.6, 0.8])
    for _, grp in df.groupby('feedtype_path_id'):
        row = grp.iloc[0]
        path = "%s\n-> %s" % (row['origin'], row['relay'])
        ax.plot(grp['entry_added'], grp['avg_latency'], label=path)

    ax.legend(bbox_to_anchor=(1.01, 1), loc=2, borderaxespad=0.,
              fontsize=12)
    ax.set_title(("%s [%s]\n%s to %s UTC"
                  ) % (host, feedtype,
                       df['entry_added'].min().strftime("%Y%m%d/%H%M"),
                       df['entry_added'].max().strftime("%Y%m%d/%H%M")))
    ax.grid(True)
    if logopt.upper() == 'LOG':
        ax.set_yscale('log')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hz\n%-d %b"))
    ax.set_ylabel("Average Latency [s]")
    sys.stdout.write("Content-type: image/png\n\n")
    plt.savefig(sys.stdout)


def plot_latency_histogram(feedtype, host):
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    req = requests.get(("http://rtstats.local/services/host/%s/rtstats.json"
                        "?feedtype=%s") % (host, feedtype))
    if req.status_code != 200:
        sys.stdout.write("Content-type: text/plain\n\n")
        sys.stdout.write("API Service Failure...")
        return

    j = req.json()
    df = pd.DataFrame(j['data'], columns=j['columns'])
    df['entry_added'] = pd.to_datetime(df['entry_added'])
    (_, ax) = plt.subplots(1, 1, figsize=(11, 7))
    data = df['avg_latency'].values
    desc = df['avg_latency'].describe(percentiles=[0.75, 0.90, 0.95, 0.99])
    for v, c in zip([75, 90, 95, 99], ['r', 'b', 'g', 'k']):
        value = desc['%s%%' % (v,)]
        ax.axvline(value, label="%s%% %.2fs" % (v, value), color=c, lw=2)
    ax.hist(data, 50, normed=False,
            weights=np.zeros_like(data) + 100. / data.size)
    ax.set_title(("%s [%s]\n%s to %s UTC"
                  ) % (host, feedtype,
                       df['entry_added'].min().strftime("%Y%m%d/%H%M"),
                       df['entry_added'].max().strftime("%Y%m%d/%H%M")))
    ax.grid(True)
    ax.legend(loc='best')
    ax.set_ylabel("Percent [%]")
    ax.set_xlabel("Latency [s]")
    sys.stdout.write("Content-type: image/png\n\n")
    plt.savefig(sys.stdout)


def plot_volume_or_prods(feedtype, host, col):
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    req = requests.get(("http://rtstats.local/services/host/%s/hourly.json"
                        "?feedtype=%s") % (host, feedtype))
    if req.status_code != 200:
        sys.stdout.write("Content-type: text/plain\n\n")
        sys.stdout.write("API Service Failure...")
        return

    j = req.json()
    df = pd.DataFrame(j['data'], columns=j['columns'])
    df['valid'] = pd.to_datetime(df['valid'])
    df['path'] = df['origin'] + "_v_" + df['relay']
    df['nbytes'] /= (1024.*1024.*1024.)  # convert to GiB
    _ = plt.figure(figsize=(11, 7))
    ax = plt.axes([0.1, 0.1, 0.6, 0.8])
    pdf = df[['valid', 'path', col]].pivot('valid', 'path', col)
    floor = np.zeros(len(pdf.index))
    colors = plt.get_cmap('rainbow')(np.linspace(0, 1, len(pdf.columns)))
    for i, path in enumerate(pdf.columns):
        tokens = path.split("_v_")
        lbl = "%s\n-> %s" % (tokens[0], tokens[1])
        ax.bar(pdf.index.values, pdf[path].values, width=1/24.,
               bottom=floor, fc=colors[i], label=lbl, align='center')
        floor += pdf[path].values
    ax.legend(bbox_to_anchor=(1.01, 1), loc=2, borderaxespad=0.,
              fontsize=12)
    ax.set_ylabel("GiB" if col == 'nbytes' else 'Number of Products')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hz\n%-d %b"))
    ax.set_title(("%s [%s]\n%s through %s UTC"
                  ) % (host, feedtype,
                       df['valid'].min().strftime("%Y%m%d/%H%M"),
                       df['valid'].max().strftime("%Y%m%d/%H%M")))
    ax.grid(True)
    sys.stdout.write("Content-type: image/png\n\n")
    plt.savefig(sys.stdout)


def main():
    uri = os.environ.get('REQUEST_URI', '')
    if uri.startswith('/cgi-bin/rtstats/siteindex'):
        host = os.environ.get('QUERY_STRING', '')[:256]
        if host == '':
            handle_siteindex()
        else:
            handle_site(host)
    elif uri.startswith('/cgi-bin/rtstats/iddstats_nc'):
        tokens = os.environ.get('QUERY_STRING', '')[:256].split("+")
        if len(tokens) == 1:
            tokens = ['IDS|DDPLUS', tokens[0], '']
        elif len(tokens) == 2:
            tokens = [tokens[0], tokens[1], '']
        plot_latency(*tokens)
    elif uri.startswith('/cgi-bin/rtstats/iddbinstats_nc'):
        tokens = os.environ.get('QUERY_STRING', '')[:256].split("+")
        if len(tokens) == 1:
            tokens = ['IDS|DDPLUS', tokens[0]]
        plot_latency_histogram(*tokens)
    elif (uri.startswith('/cgi-bin/rtstats/iddstats_vol_nc') or
            uri.startswith('/cgi-bin/rtstats/iddstats_num_nc')):
        col = "nbytes" if uri.find('_vol_nc') > -1 else 'nprods'
        tokens = os.environ.get('QUERY_STRING', '')[:256].split("+")
        if len(tokens) == 1:
            tokens = ['IDS|DDPLUS', tokens[0]]
        plot_volume_or_prods(tokens[0], tokens[1], col)
    elif uri.startswith('/cgi-bin/rtstats/iddstats_topo_nc'):
        tokens = os.environ.get('QUERY_STRING', '')[:256].split("+")
        handle_topology(tokens[1], tokens[0])
    elif uri.startswith('/cgi-bin/rtstats/rtstats_summary_volume'):
        tokens = os.environ.get('QUERY_STRING', '')[:256].split("+")
        if len(tokens) == 1:
            handle_volume_stats(tokens[0])
        else:
            handle_volume_stats_plot(tokens[0])
    else:
        # TODO: disable in production
        sys.stdout.write("Content-type: text/plain\n\n")
        for k, v in os.environ.iteritems():
            sys.stdout.write("%s -> %s\n" % (k, v))

if __name__ == '__main__':
    main()
    # handle_volume_stats('metfs1.agron.iastate.edu')
    # handle_topology('chucknorris.agron.iastate.edu', 'EXP')
