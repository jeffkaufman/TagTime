#!/usr/bin/python

"""

Reads a TagTime logfile, as for example produced by the TagTime app, and
displays it in various ways.

Currently supported are:

    - A pie chart of the total percentage time spent on a task
    - Bar charts showing which tags were active
      - on a specific day of the week
      - on a specific hour of the day
    - A line plot showing (long term) trends, summed over specified intervals

The plots can be configured from command line, especially:

    - which tags are to be shown (specific)
    - automatically select the top N tags
    - whether to show the 'other' category in the plots as well
    - the hour resolution in the hour of the day plot
    - the color map (http://wiki.scipy.org/Cookbook/Matplotlib/Show_colormaps)

REQUIREMENTS

This script relies heavily on the pandas module, which does most of the work.

"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from collections import defaultdict
import datetime
import re


def reldate(s):
    m = re.search(r'^(\d+)([DWM])', s)
    n = int(m.group(1))
    f = m.group(2)
    if f == 'D':
        d = datetime.date.today() - datetime.timedelta(days=n)
    elif f == 'W':
        d = datetime.date.today() - datetime.timedelta(weeks=n)
    elif f == 'M':
        d = datetime.date.today() - datetime.timedelta(weeks=n * 4)
    else:
        raise RuntimeError("Unknown relative date format: %s" % s)
    return datetime.datetime(d.year, d.month, d.day)


def dt2d(dt):
    return datetime.date(dt.year, dt.month, dt.day)


class TagTimeLog:
    def __init__(self, filename, interval=.75, startend=[None, None],
                 multitag='first', cmap="Paired", skipweekdays=[],
                 skiptags=[], obfuscate=False, show_now=True, smooth=True,
                 sigma=1.0):
        self.skipweekdays = skipweekdays
        self.skiptags = skiptags
        self.interval = interval
        self.multitag = multitag
        self.cmap = plt.cm.get_cmap(cmap)
        self.obfuscate = obfuscate
        self.show_now = show_now
        self.smooth = smooth
        self.sigma = sigma
        if isinstance(filename, str):
            with open(filename, "r") as log:
                self._parse_file(log)
        else:
            self._parse_file(filename)

        if startend[0] is None:
            startend[0] = datetime.datetime.fromtimestamp(1)
        if startend[1] is None:
            startend[1] = datetime.datetime.now()

        self.D = self.D.ix[startend[0]:startend[1]]

        self.rng = "%s -- %s" % (str(dt2d(self.D.index.min())),
                                 str(dt2d(self.D.index.max())))

        #self.D = self.D.fillna(0)

    def _parse_file(self, handle):
        D = defaultdict(list)
        V = defaultdict(list)
        n_excluded = 0
        interval = self.interval

        # use gaussian weights around true measurement to smooth data
        offsetlist = np.array([0.])
        offsetinterval = (4 * self.sigma + 1) / 15
        if self.smooth:
            #offsetlist = np.array([-.75, -0.5, -0.25, 0., 0.25, 0.5, 0.75])
            offsetlist = np.arange(-2 * self.sigma, 2 * self.sigma, offsetinterval)
            offsetlist += np.random.uniform(-0.1, 0.1, size=offsetlist.shape)
        weights = np.exp(- offsetlist ** 2 / self.sigma ** 2)
        weights /= weights.sum()
        print weights

        for line in handle:
            line = re.sub(r'\s*\[.*?\]\s*$', '', line)
            fields = re.split(r'\s+', line)
            dt = datetime.datetime.fromtimestamp(int(fields[0]))
            tags = fields[1:]

            tags = [x for x in tags if x not in self.skiptags]

            if self.multitag == 'first':
                tags = tags[:1]

            for t in tags:
                duration = interval
                if self.multitag == 'split':
                    duration /= len(tags)

                for weight, offset in zip(weights, offsetlist):
                    dtx = dt + datetime.timedelta(hours=offset * interval)
                    if dtx.weekday() in self.skipweekdays:
                        n_excluded += 1
                        continue
                    D[t].append(dtx)
                    V[t].append(weight * duration)
        print "Excluded %d entries" % n_excluded

        for f in D.keys():
            D[f] = pd.Series(V[f], index=D[f])

        self.D = pd.DataFrame(D)

    def trend(self, tags, top_n=None, other=False, resample='D'):
        """ show the supplied tags summed up per day """
        if top_n is not None:
            tags = self.top_n_tags(top_n, tags)
        D = self.D[tags] if tags is not None else self.D
        if other:
            D['other'] = self.D[[t for t in self.D.keys() if t not in tags]].sum(axis=1)
        D = D.resample(resample, how='sum', label='left')
        self._obfuscate(D)
        colors = self.cmap(np.linspace(0., 1., len(D.keys())))
        D = D.fillna(0)
        ax = D.plot(linewidth=2)
        for c, l in zip(colors, ax.get_lines()):
            l.set_c(c)
            ax.grid(True)
        ax.legend(loc='best')
        leg = ax.get_legend()
        for c, l in zip(colors, leg.legendHandles):
            l.set_linewidth(10)
            l.set_c(c)
        plt.ylabel('Time Spent (h) per Interval (%s)' % resample)
        plt.xlabel('Interval ID')

    def hour_of_the_week(self, tags, top_n, resolution=2, other=False):
        """ show the supplied tags summed up per hour """
        if top_n is not None:
            tags = self.top_n_tags(top_n, tags)
        if tags is None:
            tags = self.top_n_tags(1000)  # sorted ;)
        D = self.D[tags] if tags is not None else self.D
        if other:
            D['other'] = self.D[[t for t in self.D.keys() if t not in tags]].sum(axis=1)
        D = D.groupby([D.index.weekday, resolution * (D.index.hour / resolution)], sort=True).sum()
        V = D.sum(axis=1)
        for k in D.keys():
            D[k] = D[k] * 60 / V
        colors = self.cmap(np.linspace(0., 1., len(D.keys())))
        D = D.fillna(0)
        self._obfuscate(D)
        ax = D.plot(kind='bar', stacked=True, color=colors)
        for c, l in zip(colors, ax.get_lines()):
            l.set_c(c)
            ax.grid(True)
        ax.legend(loc='best')
        ax.get_legend()
        #for c, l in zip(colors, leg.legendHandles):
            #l.set_linewidth(10)
            #l.set_c(c)
        plt.ylabel('Minutes')
        plt.xlabel('Hour of the Week')
        plt.ylim(0, 60)

    def _obfuscate(self, D):
        import string
        import random
        if self.obfuscate:
            keys = D.keys()
            for k in keys:
                if k in ['other']:
                    continue
                k2 = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(4))
                D.rename(columns={k: k2}, inplace=True)

    def hour_sums(self, tags, top_n, resolution=2, other=False):
        """ show the supplied tags summed up per hour """
        if top_n is not None:
            tags = self.top_n_tags(top_n, tags)
        if tags is None:
            tags = self.top_n_tags(1000)  # sorted ;)
        D = self.D[tags] if tags is not None else self.D
        if other:
            D['other'] = self.D[[t for t in self.D.keys() if t not in tags]].sum(axis=1)
        D = D.groupby(resolution * (D.index.hour / resolution), sort=True).sum()
        V = D.sum(axis=1)
        for k in D.keys():
            D[k] = D[k] * 60 / V
        colors = self.cmap(np.linspace(0., 1., len(D.keys())))
        self._obfuscate(D)
        now = datetime.datetime.now().hour + datetime.datetime.now().minute / 60.
        if self.multitag == 'double':
            D = D.fillna(0)
            if len(D.keys()) < 8:
                Dmax = D.max().max()
                axes = D.plot(style=["-*" for c in colors], subplots=True, sharex=True, linewidth=2)
                for c, ax in zip(colors, axes):
                    ax.get_lines()[0].set_c(c)
                    if self.show_now:
                        ax.axvline(x=now, color='black')
                    ax.set_ylim(0, Dmax)
                    ax.grid(True)
                    ax.legend(loc='best')
                    leg = ax.get_legend()
                    for l, t in zip(leg.legendHandles, leg.get_texts()):
                        l.set_c(c)
                plt.gcf().subplots_adjust(hspace=0.0, wspace=0.0)
            else:
                ax = D.plot(style=["-*" for c in D.keys()], linewidth=3)
                if self.show_now:
                    ax.axvline(x=now, color='black')
                for c, l in zip(colors, ax.get_lines()):
                    l.set_c(c)
                ax.legend(loc='best')
                leg = ax.get_legend()
                for c, l, t in zip(colors, leg.legendHandles, leg.get_texts()):
                    l.set_linewidth(10)
                    l.set_c(c)
                ax.set_ylim(0)
                ax.grid(True)
        else:
            ax = D.plot(kind='bar', stacked=True, color=colors)
            if self.show_now:
                ax.axvline(x=now / resolution, label='now', color='red')
        plt.suptitle(self.rng)
        plt.ylabel('Minutes')
        plt.xlabel('Hour of the Day')
        plt.ylim(0, 60)

    def day_of_the_week_sums(self, tags, top_n=None, other=False):
        if top_n is not None:
            tags = self.top_n_tags(top_n, tags)
        if tags is None:
            tags = self.top_n_tags(1000)  # sorted ;)
        D = self.D[tags] if tags is not None else self.D
        if other:
            D['other'] = self.D[[t for t in self.D.keys() if t not in tags]].sum(axis=1)
        D = D.resample('D', how='sum', label='left').fillna(0)  # sum up within days
        D = D / D.sum(axis=1)  # all records within a day must sum to 1
        D = D.groupby(D.index.weekday, sort=True).mean()  # take average over weeks
        V = D.sum(axis=1)
        for k in D.keys():
            D[k] = D[k] * 24 / V
        self._obfuscate(D)
        colors = self.cmap(np.linspace(0., 1., len(D.keys())))
        if self.multitag == 'double':
            if len(D.keys()) < 8:
                Dmax = D.max().max()
                axes = D.plot(style=["-*" for c in colors], subplots=True, sharex=True, linewidth=2)
                for c, ax in zip(colors, axes):
                    #from IPython import embed; embed()
                    if self.show_now:
                        ax.axvline(x=(datetime.datetime.now().weekday()), label='today', color='black')
                    ax.get_lines()[0].set_c(c)
                    ax.set_xlim(-0.1, 6.1)
                    ax.set_ylim(0, Dmax)
                    ax.grid(True)
                plt.gcf().subplots_adjust(hspace=0.0, wspace=0.0)
            else:
                ax = D.plot(style=["-*" for c in D.keys()], linewidth=3)
                if self.show_now:
                    ax.axvline(x=(datetime.datetime.now().weekday()), label='today', color='black')
                for c, l in zip(colors, ax.get_lines()):
                    l.set_c(c)
                ax.set_ylim(0)
                ax.set_xlim(-0.1, 6.1)
                ax.grid(True)
            plt.xticks(np.arange(7), list("MTWTFSS"))
        else:
            D.plot(kind='bar', stacked=True, color=colors)
            plt.ylim(0, 24)
            plt.xticks(np.arange(7) + 0.5, list("MTWTFSS"))
        plt.suptitle('Time Spent over Day of the Week')
        plt.legend(loc='best')
        plt.xlabel('Day of the Week')
        plt.ylabel('Time Spent (h)')

    def top_n_tags(self, n, extra_tags):
        # sum up tags within a day, determine the sum over the days
        D = self.D.resample('D', how='sum', label='left').sum()
        keys = sorted(D.keys(), key=lambda x: D[x], reverse=True)
        keys = keys[:n]

        if extra_tags is None:
            return keys

        for x in extra_tags:
            if x in keys:
                continue
            keys.append(x)
        return keys

    def pie(self, tags, top_n=None, other=False):
        """
        Show a pie-chart of how time is spent.
        """

        if top_n is not None:
            tags = self.top_n_tags(top_n, tags)
        D = self.D[tags] if tags is not None else self.D
        if other:
            D['other'] = self.D[[t for t in self.D.keys() if t not in tags]].sum(axis=1)

        # sum up tags within a day, determine the mean over the days
        self._obfuscate(D)
        D = D.resample('D', how='sum', label='left').fillna(0).mean()

        # sort by time spent
        keys = sorted(D.keys(), key=lambda x: D[x], reverse=True)
        values = [D[x] for x in keys]

        idx = np.where(~np.isnan(values))
        keys = np.array(keys)[idx]
        values = np.array(values)[idx]

        # reformat labels to include absolute hours
        keys = ["%s (%1.1f h)" % (x, D[x]) for x in keys]

        fig = plt.figure()
        ax = fig.add_subplot(111)
        colors = self.cmap(np.linspace(0., 1., len(values)))
        pie_wedge_collection = ax.pie(values, labels=keys, autopct='%1.1f%%', colors=colors, labeldistance=1.05)
        for pie_wedge in pie_wedge_collection[0]:
                pie_wedge.set_edgecolor('white')


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('logfile', type=argparse.FileType('r'), help='the logfile to analyze')
    parser.add_argument('--pie', action='store_true', help='display a pie chart for total time spent')
    parser.add_argument('--day-of-the-week', action='store_true', help='display a bar for each day of the week')
    parser.add_argument('--trends', action='store_true', help='show a line chart of time spent in trend-interval')
    parser.add_argument('--trend-interval', default='W', help='the interval to sum over for trend calculation (e.g. 2D, 7D, ...)')
    parser.add_argument('--hour-of-the-day', action='store_true', help='display a bar for each hour of the day')
    parser.add_argument('--hour-of-the-week', action='store_true', help='display a bar for each hour of the day')
    parser.add_argument('--exclude-weekdays', default=[], type=lambda s: [int(x) for x in s], help='skip days of the week (Delimiter-free list of integers, e.g. 01 -> skip monday and tuesday)')
    parser.add_argument('--include-weekdays', default=np.arange(7), type=lambda s: np.array([int(x) for x in s]), help='keep only these days of the week (Delimiter-free list of integers, e.g. 01 -> keep monday and tuesday)')
    parser.add_argument('--exclude-tags', default=[], type=lambda s: [x for x in s.split(",")], help='skip tags (comma-delimited list of strings)')
    parser.add_argument('--resolution', type=int, default=2, help='the number of consecutive hours summed over in hour-of-the-XXX chart')
    parser.add_argument('--top-n', type=int, help='limit the tags acted upon to the N most popular')
    parser.add_argument('--other', action='store_true', help='show the category "other"')
    parser.add_argument('--tags', nargs='*', help='limit the tags acted upon')
    parser.add_argument('--interval', type=float, default=.75, help='the expected time between two pings, in fractions of hours')
    parser.add_argument('--multitag', type=str, default='first', help='''how to deal with one ping with multiple tags:
                        first (default) -- only first tag is used
                        split -- split timeinterval equally among tags
                        double -- treat as one ping separate for every tag''')
    #parser.add_argument('--double-count', action='store_true', help='one ping with multiple tags is treated as one ping separate for every tag (default off=time is split equally between tags)')
    parser.add_argument('--rstart', type=reldate, help='relative start date of interval, inclusive (2D: 2 days ago, 2W: 2 Weeks ago)')
    parser.add_argument('--rend',   type=reldate, help='relative end date of interval, exclusive')
    parser.add_argument('--start', type=lambda x: datetime.datetime.strptime(x, '%Y-%m-%d'), help='start date of interval, inclusive (YYYY-MM-DD)')
    parser.add_argument('--end',   type=lambda x: datetime.datetime.strptime(x, '%Y-%m-%d'), help='end date of interval, exclusive (YYYY-MM-DD)')
    parser.add_argument('--cmap',   default='Paired', help='color map for graphs, see http://wiki.scipy.org/Cookbook/Matplotlib/Show_colormaps')
    parser.add_argument('--obfuscate', action='store_true', help='show plot, but obfuscate tag names')
    parser.add_argument('--no-now', action='store_false', help='do not display a line for the current day/time')
    parser.add_argument('--smooth-sigma', type=float, default=0.25, help='sigma to smooth observations with, in multiples of interval')
    parser.add_argument('--no-smooth', action='store_false', help='do not spread the pings over the interval around the real ping time')
    args = parser.parse_args()

    if len(args.include_weekdays) != 7:
        args.exclude_weekdays = np.setdiff1d(np.arange(7), args.include_weekdays)

    if datetime.datetime.now().weekday() in args.exclude_weekdays:
        args.no_now = False

    if args.rstart is not None:
        args.start = args.rstart
    if args.rend is not None:
        args.end = args.rend

    ttl = TagTimeLog(args.logfile, interval=args.interval,
                     startend=[args.start, args.end],
                     multitag=args.multitag,
                     cmap=args.cmap,
                     skipweekdays=args.exclude_weekdays,
                     skiptags=args.exclude_tags,
                     obfuscate=args.obfuscate,
                     show_now=args.no_now,
                     smooth=args.no_smooth,
                     sigma=args.smooth_sigma)
    if(args.pie):
        ttl.pie(args.tags, args.top_n, args.other)
    if(args.day_of_the_week):
        ttl.day_of_the_week_sums(args.tags, args.top_n, args.other)
    if(args.hour_of_the_day):
        ttl.hour_sums(args.tags, args.top_n, resolution=args.resolution, other=args.other)
    if(args.hour_of_the_week):
        ttl.hour_of_the_week(args.tags, args.top_n, resolution=args.resolution, other=args.other)
    if(args.trends):
        ttl.trend(args.tags, args.top_n, args.other, args.trend_interval)

    plt.show()


if __name__ == '__main__':
    main()
