"""Build the Zheyou client from the pinned upstream executable."""

from hashlib import sha256
from pathlib import Path
import re
from struct import pack_into, unpack_from

import brotli


ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = "346e5bb3f15d5da683c43ab1176778764b5fe04cc93c985e1962884a79bd2ee5"
ASSET_OFFSET = 0x1122A59
ASSET_CAPACITY = 1676035
LENGTH_OFFSET = 0x12CFB98
EXECUTABLE = "ZheyouClient.exe"
PENDING = "ZheyouClient.next.exe"
REDRAW_BRANCH = 0x15749F
REDRAW_PANIC = 0x158A6D
REDRAW_DISPATCH = 0x157A23


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Unexpected UI bundle: {before!r}")
    return source.replace(before, after)


def allow_reentrant_redraw(package):
    # Match Tao's WM_PAINT recovery: if the outer redraw owns the flush,
    # skip the completion callbacks and delegate the message to Windows.
    # https://github.com/tauri-apps/tao/pull/1410
    next_instruction = REDRAW_BRANCH + 6
    target = next_instruction + unpack_from("<i", package, REDRAW_BRANCH + 2)[0]
    if package[REDRAW_BRANCH - 2:REDRAW_BRANCH + 2] != b"\x84\xc0\x0f\x84" or target != REDRAW_PANIC:
        raise ValueError("Unexpected Windows redraw branch in the base executable")
    pack_into("<i", package, REDRAW_BRANCH + 2, REDRAW_DISPATCH - next_instruction)


def main():
    package = bytearray((ROOT / "vendor" / "akagi.exe").read_bytes())
    if sha256(package).hexdigest() != ORIGINAL:
        raise ValueError("Expected the original AkagiMS 1.3.2 Windows x64 akagi.exe in vendor/")
    # Carry forward the two original local full-auto patches for this build.
    for offset, before, after in (
        (0x78C909, "80bbcc00000001", "eb379090909090"),
        (0x7DFBB3, "4584ff0f842b070000488dbe6001", "488dbe600100004584ff0f84d40b"),
    ):
        expected = bytes.fromhex(before)
        if package[offset:offset + len(expected)] != expected:
            raise ValueError(f"Unexpected executable bytes at {offset:#x}")
        package[offset:offset + len(expected)] = bytes.fromhex(after)
    allow_reentrant_redraw(package)
    remote = b"https://mjapi.shinkuan.me"
    local = b"http://127.0.0.1:25034/"
    package[:] = replace_once(package, remote, local.ljust(len(remote), b"/"))
    length = unpack_from("<Q", package, LENGTH_OFFSET)[0]
    source = brotli.decompress(package[ASSET_OFFSET:ASSET_OFFSET + length])
    source = replace_once(source, b"if(a===`full`&&!l){Uw.info(e(`game.full_needs_key`));return}if(a===`auto`",
                          b"if((a===`auto`||a===`full`)")
    source = replace_once(source, b"let r=t===`full`&&!l;return(0,G.jsx)(`button`,{type:`button`,\"aria-pressed\":u===t,title:r?e(`game.full_needs_key`):void 0,",
                          b"return(0,G.jsx)(`button`,{type:`button`,\"aria-pressed\":u===t,")
    source = replace_once(source, b"r?`text-muted-foreground/50 hover:text-muted-foreground`:", b"")
    component = b"\n".join(Path(__file__).with_name(name).read_bytes()
                           for name in ("selector.js", "recommendation.js"))
    source = replace_once(source, b"return await V(e,t)}async function UC", b"return await zheyouLocalApi(e,t)}async function UC")
    for start_name, end_name, replacement in (
        (b"var BD=3e3,VD=3e4,", b"var eO=", b""),
        (b"function U9(", b"var G9=", b""),
        (b"function Gne(", b"function Kne(", "function Gne(){return G.jsx(`p`,{children:`三麻与四麻模型均在本机运行。`})}".encode()),
        (b"var JC=`1.3.2`,YC=[", b"function XC(", b"var JC=`0.1.0`,YC=[];"),
        (b"function PC(", b"var IC;", b"function PC({className:e}){return G.jsx(`span`,{className:W(`font-semibold`,e),children:`Z`})}"
         b"function FC({className:e}){return G.jsx(`span`,{className:W(`font-semibold`,e),children:`Zheyou`})}"),
        (b"function zne(", b"var Q9=", b"function zne(){return G.jsxs(`p`,{className:`text-sm`,children:"
         b"[`Zheyou v`,JC,` | `,G.jsx(`button`,{type:`button`,className:`underline`,onClick:()=>qC(WC+`/releases`),children:`GitHub Releases`})]})}"),
    ):
        start = source.index(start_name)
        end = source.index(end_name, start)
        source = source[:start] + replacement + source[end:]
    source = replace_once(source, b",(0,G.jsx)($D,{})", b"")
    source = replace_once(source, b",(0,G.jsx)(kne,{})", b"")
    source = replace_once(source, b"var WC=`https://github.com/shinkuan/Akagi`,GC=`https://github.com/shinkuan/AkagiMS`,KC=`https://discord.gg/Z2wjXUK8bN`;", b"var WC=`https://github.com/zgozh/zheyou-majsoul`,GC=WC;")
    source = replace_once(source, b",(0,G.jsx)(uw,{label:`Discord`,collapsed:!h,onClick:()=>qC(KC),children:(0,G.jsx)(kC,{className:`h-4 w-4`})})", b"")
    source = replace_once(source, b",(0,G.jsxs)(J,{variant:`outline`,size:`sm`,onClick:()=>qC(KC),children:[(0,G.jsx)(kC,{className:`h-4 w-4 mr-1.5`}),`Discord`]})", b"")
    source = replace_once(source, b"(0,G.jsx)(uw,{label:e(`sidebar.announcements`),collapsed:!h,onClick:()=>$C.getState().openHistory(),children:(0,G.jsx)(Rc,{className:`h-4 w-4`})}),", b"")
    source = replace_once(source, b"(0,S.useEffect)(()=>{HC&&El().then(m).catch(()=>{})},[]),", b"")
    source = source.replace(b"akagi.", b"zheyou.")
    source = re.sub(rb"\bAkagi(?:MS)?\b", "柘栯".encode(), source)
    source = replace_once(source, b"function wee(){", component + b"\nfunction wee(){")
    source = replace_once(source, b"{href:`/review`,label:e(`nav.review`),icon:Yc},", b"")
    source = replace_once(source, b"{path:`review`,element:(0,G.jsx)($te,{})},", b"")
    source = source.replace(b"t(`setup.finish.bots_cloud`)", b"`Epsilon / Mortal-S42`")
    anchor = b"children:e(n)},t)})}),a&&(0,G.jsx)(See"
    source = replace_once(source, anchor, b"children:e(n)},t)})}),G.jsx(ZheyouLocalModelSelector,{}),a&&(0,G.jsx)(See")
    warning = (b"i&&(0,G.jsx)(`span`,{className:`shrink-0 rounded bg-amber-500/20 px-1.5 py-0.5 text-[11px] text-amber-500`,"
               b"title:e(`game.cloud_degraded_hint`),children:e(`game.cloud_degraded`)})")
    source = replace_once(source, warning, b"i&&G.jsx(ZheyouInferenceWarning,{})")
    anchor = b"children:e(`game.player_n`,{n:s+1})})]}),(0,G.jsx)(`dl`,{className:`flex justify-between text-xs`"
    source = replace_once(source, anchor, b"children:e(`game.player_n`,{n:s+1})})]}),G.jsx(ZheyouLocalReconnect,{}),"
                          b"(0,G.jsx)(`dl`,{className:`flex justify-between text-xs`")
    source = replace_once(source,
        b"events:[],responses:[],notifications:[],pushEvent:t=>e(e=>({events:BT([...e.events,zT(t)],Iee)})),pushResponse:t=>e(e=>({responses:BT([...e.responses,zT(t)],IT)}))",
        b"events:[],responses:[],notifications:[],recommendationEvents:[],recommendationSeat:null,"
        b"pushEvent:t=>e(e=>({events:BT([...e.events,zT(t)],Iee),"
        b"recommendationEvents:t.type===`start_game`?[]:t.type===`start_kyoku`?[t]:"
        b"e.recommendationEvents.length?[...e.recommendationEvents,t]:e.recommendationEvents,"
        b"recommendationSeat:t.type===`start_game`?t.id:e.recommendationSeat})),"
        b"pushResponse:t=>e(e=>({responses:BT([...e.responses,zT({...t,meta:zheyouModelMeta(t.meta),_recommendationEvents:e.recommendationEvents,"
        b"_recommendationSeat:e.recommendationSeat})],IT)}))")
    source = replace_once(source, b"function wD(){let e=VT(e=>e.responses),",
        b"function wD(){let e=VT(e=>e.responses),round=VT(e=>e.recommendationEvents[0]),")
    source = replace_once(source,
        b"c=(0,S.useMemo)(()=>{for(let t=e.length-1;t>=0;t--){let n=_D(e[t].meta);if(n)return yD(n,Ree)}return[]},[e]);",
        b"[recommendation,c]=(0,S.useMemo)(()=>{for(let t=e.length-1;t>=0;t--){let n=_D(e[t].meta);"
        b"if(n)return [e[t],yD(n,Ree)]}return [null,[]]},[e]);")
    source = replace_once(source, b"className:W(`flex items-center gap-2 rounded px-2 py-1.5`,i&&`bg-yellow-500/15`)",
        b"className:W(`rounded`,i&&`bg-yellow-500/15`)")
    source = replace_once(source,
        b"gD(e.color,.08)}:void 0,children:[(0,G.jsxs)(`span`,{className:`w-6 shrink-0 font-mono text-[11px] text-muted-foreground`",
        b"gD(e.color,.08)}:void 0,children:[G.jsxs(`div`,{className:`flex items-center gap-2 px-2 py-1.5`,children:["
        b"(0,G.jsxs)(`span`,{className:`w-6 shrink-0 font-mono text-[11px] text-muted-foreground`")
    source = replace_once(source, b"children:e.value})]})]},`${e.label??``}-${a}-${t}`)",
        b'"data-recommendation-preference":"",children:ZheyouRecommendationValue(recommendation,e.value)})]})]}),'
        b"i&&round===recommendation?._recommendationEvents[0]&&"
        b"G.jsx(ZheyouRecommendationNote,{response:recommendation,first:e})]},`${e.label??``}-${a}-${t}`)")
    packed = brotli.compress(source, quality=11, lgwin=22)
    if len(packed) > ASSET_CAPACITY or brotli.decompress(packed) != source:
        raise ValueError("Updated UI could not be written into the existing asset slot")
    package[ASSET_OFFSET:ASSET_OFFSET + ASSET_CAPACITY] = packed.ljust(ASSET_CAPACITY, b"\0")
    pack_into("<Q", package, LENGTH_OFFSET, len(packed))
    result = ROOT / EXECUTABLE
    pending = ROOT / PENDING
    pending.write_bytes(package)
    try:
        pending.replace(result)
    except PermissionError:
        result = pending
    print(f"{result.name} {sha256(package).hexdigest()} ({len(packed)}-byte UI)")


if __name__ == "__main__":
    main()
