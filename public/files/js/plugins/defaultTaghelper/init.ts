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

/// <reference path="../../../ts/declarations/common.d.ts" />
/// <reference path="../../../ts/declarations/popupbox.d.ts" />
/// <amd-dependency path="./view" name="view" />

import stores = require('./stores');
declare var view:any;


export function getPopupBoxRenderer(pluginApi:Kontext.PluginApi,
        insertCallback:(value:string)=>void, widgetId:number):(box:PopupBox.TooltipBox, finalize:()=>void)=>void {

    let tagHelperStore = new stores.TagHelperStore(pluginApi, widgetId);

    return function (box:PopupBox.TooltipBox, finalize:()=>void) {
        pluginApi.renderReactComponent(
            view.init(pluginApi.dispatcher(), pluginApi.exportMixins(), tagHelperStore).TagBuilder,
            box.getRootElement(),
            {
                widgetId: widgetId,
                doneCallback: () => {
                    finalize();
                },
                insertCallback: (v:string) => {
                    insertCallback(v);
                    box.close()
                },
                initialTagValue: '.*'
            }
        );
    };
}