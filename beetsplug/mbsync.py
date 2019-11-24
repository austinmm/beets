# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Jakob Schnitzer.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Update library's tags using MusicBrainz.
"""
from __future__ import division, absolute_import, print_function

from beets.plugins import BeetsPlugin, apply_item_changes
from beets import autotag, library, ui, util
from beets.autotag import hooks
from collections import defaultdict

import re

MBID_REGEX = r"(\d|\w){8}-(\d|\w){4}-(\d|\w){4}-(\d|\w){4}-(\d|\w){12}"


class MBSyncPlugin(BeetsPlugin):

    def __init__(self, lib=None, move=None,
                 pretend=None, write=None, query=None):
        super(MBSyncPlugin, self).__init__()
        self.lib = lib
        self.move = move
        self.pretend = pretend
        self.write = write
        self.query = query

    def commands(self):
        cmd = ui.Subcommand('mbsync',
                            help=u'update metadata from musicbrainz')
        cmd.parser.add_option(
            u'-p', u'--pretend', action='store_true',
            help=u'show all changes but do nothing')
        cmd.parser.add_option(
            u'-m', u'--move', action='store_true', dest='move',
            help=u"move files in the library directory")
        cmd.parser.add_option(
            u'-M', u'--nomove', action='store_false', dest='move',
            help=u"don't move files in library")
        cmd.parser.add_option(
            u'-W', u'--nowrite', action='store_false',
            default=None, dest='write',
            help=u"don't write updated metadata to files")
        cmd.parser.add_format_option()
        cmd.func = self.func
        return [cmd]

    def func(self, lib, opts, args):
        """Command handler for the mbsync function.
        """
        self = MBSyncPlugin(
            lib=lib,
            move=ui.should_move(opts.move),
            pretend=opts.pretend,
            write=ui.should_write(opts.write),
            query=ui.decargs(args)
        )
        self.singletons()
        self.albums()

    def singletons(self):
        """Retrieve and apply info from the autotagger for items matched by
        query.
        """
        for item in self.lib.items(self.query + [u'singleton:true']):
            item_formatted = format(item)
            if not item.mb_trackid:
                self._log.info(u'Skipping singleton with no mb_trackid: {0}',
                               item_formatted)
                continue

            # Do we have a valid MusicBrainz track ID?
            if not re.match(MBID_REGEX, item.mb_trackid):
                self._log.info(u'Skipping singleton with invalid mb_trackid:' +
                               ' {0}', item_formatted)
                continue

            # Get the MusicBrainz recording info.
            track_info = hooks.track_for_mbid(item.mb_trackid)
            if not track_info:
                self._log.info(u'Recording ID not found: {0} for track {0}',
                               item.mb_trackid,
                               item_formatted)
                continue

            # Apply.
            with self.lib.transaction():
                autotag.apply_item_metadata(item, track_info)
                apply_item_changes(self.lib, item,
                                   self.move, self.pretend, self.write)

    def albums(self):
        """Retrieve and apply info from the autotagger for albums matched by
        query and their items.
        """
        # Process matching albums.
        for albm in self.lib.albums(self.query):
            album_formatted = format(albm)
            album_info = self.validate_album(albm.mb_albumid, album_formatted)
            if album_info is None:
                continue

            items = list(albm.items())

            # Map release track and recording MBIDs to their information.
            # Recordings can appear multiple times on a release, so each MBID
            # maps to a list of TrackInfo objects.
            releasetrack_index = dict()
            track_index = defaultdict(list)
            for track_info in album_info.tracks:
                releasetrack_index[track_info.release_track_id] = track_info
                track_index[track_info.track_id].append(track_info)

            mapping = self.construct_track_mapping(
                items, releasetrack_index, track_index
                )

            # Apply.
            self._log.debug(u'applying changes to {}', album_formatted)
            with self.lib.transaction():
                autotag.apply_metadata(album_info, mapping)
                any_changed_item = self.find_changed_items(items)
                if any_changed_item is None:
                    # No change to any item.
                    continue

                if not self.pretend:
                    self.update_album_structure(albm, any_changed_item)
                    self.move_album_art(albm, items, album_formatted)

    def construct_track_mapping(self, items, releasetrack_index, track_index):
        # Construct a track mapping according to MBIDs (release track MBIDs
        # first, if available, and recording MBIDs otherwise). This should
        # work for albums that have missing or extra tracks.
        mapping = {}
        for item in items:
            if item.mb_releasetrackid and \
                    item.mb_releasetrackid in releasetrack_index:
                mapping[item] = releasetrack_index[item.mb_releasetrackid]
            else:
                candidates = track_index[item.mb_trackid]
                if len(candidates) == 1:
                    mapping[item] = candidates[0]
                else:
                    # If there are multiple copies of a recording, they are
                    # disambiguated using their disc and track number.
                    for c in candidates:
                        if (c.medium_index == item.track and
                                c.medium == item.disc):
                            mapping[item] = c
                            break
        return mapping

    def validate_album(self, albumid, album_formatted):
        if not albumid:
            self._log.info(u'Skipping album with no mb_albumid: {0}',
                           album_formatted)
            return None

        # Do we have a valid MusicBrainz album ID?
        if not re.match(MBID_REGEX, albumid):
            self._log.info(u'Skipping album with invalid mb_albumid: {0}',
                           album_formatted)
            return None

        # Get the MusicBrainz album information.
        album_info = hooks.album_for_mbid(albumid)
        if not album_info:
            self._log.info(u'Release ID {0} not found for album {1}',
                           albumid, album_formatted)
            return None

        return album_info

    def find_changed_items(self, items):
        any_changed_item = items[0]
        changed = False
        # Find any changed item to apply MusicBrainz changes to album.
        for item in items:
            item_changed = ui.show_model_changes(item)
            changed |= item_changed
            if item_changed:
                any_changed_item = item
                apply_item_changes(self.lib, item, self.move,
                                   self.pretend, self.write)
        if not changed:
            # No change to any item.
            return None
        return any_changed_item

    def update_album_structure(self, albm, any_changed_item):
        # Update album structure to reflect an item in it.
        for key in library.Album.item_keys:
            albm[key] = any_changed_item[key]
        albm.store()

    def move_album_art(self, albm, items, album_formatted):
        # Move album art (and any inconsistent items).
        if self.move and self.lib.directory in util.ancestry(items[0].path):
            self._log.debug(u'moving album {0}', album_formatted)
            albm.move()
