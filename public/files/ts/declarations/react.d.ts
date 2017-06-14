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

/**
 * This is just a simplified type specification covering only
 * functions used by KonText.
 */
declare module React {

    export interface ReactElement {
    }

    export interface Component {
    }

    export interface ReactClass {
    }

    export interface Props {
        [key:string]:any;
    }

    export function createElement(elmType:ReactClass, props:Props,
                                  ...children:any[]):ReactElement;
}

declare module ReactDOM {

    export function render(element:React.ReactElement, container:HTMLElement, callback?:()=>void);

    export function unmountComponentAtNode(element:HTMLElement):boolean;

    export function findDOMNode(component:React.ReactElement):HTMLElement;
}

declare module "vendor/react" {
    export = React;
}

declare module "vendor/react-dom" {
    export = ReactDOM;
}
