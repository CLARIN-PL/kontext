/*
 * Copyright (c) 2015 Institute of the Czech National Corpus
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

/// <reference path="./jquery.d.ts" />

interface JScrollPaneSettings {
    maintainPosition:boolean;
}

interface JQuery {
    jScrollPane(settings?:JScrollPaneSettings):void;
}

interface JQueryAjaxSettings {
    periodic?:any;
}

interface jqueryPeriodic {
    (arg:any):void;
}

declare module "vendor/jquery.periodic" {
    export = jqueryPeriodic;
}