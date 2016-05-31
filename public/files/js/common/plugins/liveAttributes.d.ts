/*
 * Copyright (c) 2016 Institute of the Czech National Corpus
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; version 2
 * dated June, 1991.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.

 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
 */

/// <reference path="../../../ts/declarations/rsvp.d.ts" />
/// <reference path="../../../ts/declarations/common.d.ts" />

declare module LiveAttributesInit {

    /**
     * Represents an object which is able to provide
     * a callback function initiated by textTypesStore
     * every time user enters a text into one of raw text inputs
     * (used whenever the number of items to display is too high).
     */
    export interface AttrValueTextInputListener extends Kontext.PageStore {
        getListenerCallback():(attrName:string, value:string)=>RSVP.Promise<any>;
    }

    export function create(pluginApi:Kontext.QueryPagePluginApi,
                     textTypesStore:TextTypes.ITextTypesStore,
                     bibAttr:string):RSVP.Promise<AttrValueTextInputListener>;

    /**
     * Return a dict containing one or more React classes representing plug-in's views
     *
     * (we are not strict about React classes as we just pass them around)
     */
    export function getViews(dispatcher:any, mixins:any, ...stores:any[]):{[name:string]:any};
}
