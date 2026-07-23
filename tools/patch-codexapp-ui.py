#!/data/data/com.termux/files/usr/bin/python
"""Apply and verify the maintained CodexApp composer extensions."""

import argparse
import os
import pathlib
import re
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSET = ROOT / "vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/index-BjdL8GKN.js"
THREAD_ASSET = (
    ROOT
    / "vendor/codexapp-native-npm/node_modules/codexapp/dist/assets/ThreadConversation-BjC7GMPc.js"
)
DIST_ROOT = ASSET.parent.parent
INDEX = DIST_ROOT / "index.html"
FRONTEND_SCRIPT_RE = re.compile(r'src="/assets/index-[^"]+\.js"')
PREMOUNT_OVERLAY_RE = re.compile(
    r'^[ \t]*<script src="/nemotron-autonomy-progress\.js[^"]*"></script>\r?\n?',
    re.MULTILINE,
)
BASE_EFFORTS = (
    '{value:"none",label:"None"},{value:"minimal",label:"Minimal"},'
    '{value:"low",label:"Low"},{value:"medium",label:"Medium"},'
    '{value:"high",label:"High"},{value:"xhigh",label:"Extra high"}'
)
PATCHED_EFFORTS = BASE_EFFORTS + ',{value:"max",label:"Max"}'
BASE_MODEL_HANDLER = 'function zr(M){o("update:selected-model",M)}'
PATCHED_MODEL_HANDLER = (
    'function zr(M){o("update:selected-model",M),'
    'window.dispatchEvent(new CustomEvent("nemotron:runtime-selection",'
    '{detail:{model:M,effort:r.selectedReasoningEffort}}))}'
)
BASE_EFFORT_HANDLER = 'function _o(M){o("update:selected-reasoning-effort",M)}'
PATCHED_EFFORT_HANDLER = (
    'function _o(M){o("update:selected-reasoning-effort",M),'
    'window.dispatchEvent(new CustomEvent("nemotron:runtime-selection",'
    '{detail:{model:r.selectedModel,effort:M}}))}'
)
BASE_CLEANUP_HANDLER = 'function Xd(){'
LEGACY_CLEANUP_HANDLER = (
    'function nemotronCleanupConverge(l){const p=l&&l.detail,'
    'T=Array.isArray(p==null?void 0:p.deletedThreadIds)?p.deletedThreadIds:[];'
    'if(p&&p.clearAllThreads===!0)for(const G of Ur(Ht))fo(G.id);'
    'else for(const G of T)typeof G=="string"&&G&&fo(G);'
    'kr({force:!0}).catch(()=>{})}function Xd(){'
)
BUGGY_STRICT_CLEANUP_HANDLER = (
    'function nemotronCleanupConverge(l){const p=l&&l.detail,'
    'T=Array.isArray(p==null?void 0:p.deletedThreadIds)?p.deletedThreadIds:[];'
    'G=()=>{if(p&&p.clearAllThreads===!0)for(const re of Ur(Ht))fo(re.id);'
    'else for(const re of T)typeof re=="string"&&re&&fo(re)};'
    'G(),kr({force:!0}).then(G).catch(()=>{})}function Xd(){'
)
PATCHED_CLEANUP_HANDLER = (
    'function nemotronCleanupConverge(l){const p=l&&l.detail,'
    'T=Array.isArray(p==null?void 0:p.deletedThreadIds)?p.deletedThreadIds:[],'
    'G=()=>{if(p&&p.clearAllThreads===!0)for(const re of Ur(Ht))fo(re.id);'
    'else for(const re of T)typeof re=="string"&&re&&fo(re)};'
    'G(),kr({force:!0}).then(G).catch(()=>{})}function Xd(){'
)
BASE_CLEANUP_MOUNT = 'window.addEventListener("focus",ef),window.addEventListener("resize",pt)'
PATCHED_CLEANUP_MOUNT = (
    'window.addEventListener("focus",ef),'
    'window.addEventListener("nemotron-autonomy:sessions-deleted",nemotronCleanupConverge),'
    'window.addEventListener("resize",pt)'
)
BASE_CLEANUP_UNMOUNT = 'window.removeEventListener("focus",ef),window.removeEventListener("resize",pt)'
PATCHED_CLEANUP_UNMOUNT = (
    'window.removeEventListener("focus",ef),'
    'window.removeEventListener("nemotron-autonomy:sessions-deleted",nemotronCleanupConverge),'
    'window.removeEventListener("resize",pt)'
)
BASE_NULL_UNSAFE_NEXT_SIBLING = 'nextSibling:e=>e.nextSibling,querySelector:e=>Sa.querySelector(e)'
LEGACY_NULL_SAFE_NEXT_SIBLING = (
    'nextSibling:e=>e==null?null:e.nextSibling,querySelector:e=>Sa.querySelector(e)'
)
DIAGNOSTIC_NULL_SIBLING = (
    'nextSibling:e=>{if(e==null)throw new Error("NemotronNullSibling");'
    'return e.nextSibling},querySelector:e=>Sa.querySelector(e)'
)
PATCHED_NULL_SAFE_NEXT_SIBLING = LEGACY_NULL_SAFE_NEXT_SIBLING
BASE_NULL_UNSAFE_PARENT_NODE = 'parentNode:e=>e.parentNode'
LEGACY_NULL_SAFE_PARENT_NODE = 'parentNode:e=>e==null?null:e.parentNode'
DIAGNOSTIC_NULL_PARENT = (
    'parentNode:e=>{if(e==null)throw new Error("NemotronNullParent");return e.parentNode}'
)
PATCHED_NULL_SAFE_PARENT_NODE = LEGACY_NULL_SAFE_PARENT_NODE
BASE_NULL_UNSAFE_REMOVE = 'remove:e=>{const t=e.parentNode;t&&t.removeChild(e)}'
LEGACY_NULL_SAFE_REMOVE = 'remove:e=>{const t=e&&e.parentNode;t&&t.removeChild(e)}'
DIAGNOSTIC_NULL_REMOVE = (
    'remove:e=>{if(e==null)throw new Error("NemotronNullRemove");'
    'const t=e.parentNode;t&&t.removeChild(e)}'
)
PATCHED_NULL_SAFE_REMOVE = LEGACY_NULL_SAFE_REMOVE
BASE_APP_BOOT = 'TC();i0(gN).use(yN).mount("#app")'
PATCHED_APP_BOOT = (
    'window.__NEMOTRON_BUNDLE_EXECUTIONS__='
    '(window.__NEMOTRON_BUNDLE_EXECUTIONS__||0)+1,'
    'window.__NEMOTRON_VUE_APP__||('
    'TC(),window.__NEMOTRON_VUE_APP__=i0(gN).use(yN),'
    'window.__NEMOTRON_VUE_APP__.mount("#app"))'
)
BASE_COMMAND_ACTIVITY = (
    'if($==="commandexecution"){const j=xe(_==null?void 0:_.command);'
    'return{threadId:c,activity:{label:"Running command",details:j?[j]:[]}}}'
)
PATCHED_COMMAND_ACTIVITY = (
    'if($==="commandexecution"){const j=xe(_==null?void 0:_.command),'
    'U=window.NemotronAutonomyProgress,'
    'Y=U&&typeof U.humanizeCommand==="function"?U.humanizeCommand(j):'
    '"Working on the requested task";'
    'return{threadId:c,activity:{label:"Working",details:Y?[Y]:[]}}}'
)
BASE_COMMAND_DELTA_ACTIVITY = (
    'return i.method==="item/commandExecution/outputDelta"?'
    '{threadId:c,activity:{label:"Running command",details:[]}}:'
)
PATCHED_COMMAND_DELTA_ACTIVITY = (
    'return i.method==="item/commandExecution/outputDelta"?'
    '{threadId:c,activity:{label:"Working",details:["Receiving the latest verified task output"]}}:'
)
BASE_SECONDARY_COMMAND_ACTIVITY = (
    'ws&&(or(_,ws),Yt(_,{label:"Running command",'
    'details:[((El=ws.commandExecution)==null?void 0:El.command)??""]}));'
)
PATCHED_SECONDARY_COMMAND_ACTIVITY = (
    'ws&&(or(_,ws),Yt(_,{label:"Working",details:[(()=>{'
    'const j=((El=ws.commandExecution)==null?void 0:El.command)??"",'
    'U=window.NemotronAutonomyProgress;'
    'return U&&typeof U.humanizeCommand==="function"?U.humanizeCommand(j):'
    '"Working on the requested task"})()]}));'
)
BASE_THREAD_COMMAND_SUMMARY = (
    'function Zn(e){var a,c;const t=Ht(e).length,'
    'i=((c=(a=e.commandExecution)==null?void 0:a.command)==null?void 0:c.trim())||"(command)";'
    'return`${t===1?"1 command":`${t} commands`} · latest: ${i}`}'
)
PATCHED_THREAD_COMMAND_SUMMARY = (
    'function Zn(e){var a,c;const t=Ht(e).length,'
    'i=((c=(a=e.commandExecution)==null?void 0:a.command)==null?void 0:c.trim())||"(command)",'
    'U=window.NemotronAutonomyProgress,'
    'Y=U&&typeof U.humanizeCommand==="function"?U.humanizeCommand(i):'
    '"Working on the requested task";'
    'return`${t===1?"1 command":`${t} commands`} · latest: ${Y}`}'
)
BASE_THREAD_STATUS_SPAN = 'd("span",$i,h(Zn(t)),1)'
PATCHED_THREAD_STATUS_SPAN = (
    'd("span",{...$i,role:"status","aria-live":"polite","aria-atomic":"true"},h(Zn(t)),1)'
)
BASE_THREAD_COMMAND_TYPE = (
    'function O(e){return e.messageType==="commandExecution"&&!!e.commandExecution}'
)
PATCHED_THREAD_COMMAND_TYPE = (
    'function nemotronGalleryResult(e){const n=e&&e.commandExecution,'
    't=(n==null?void 0:n.command)||"",i=(n==null?void 0:n.aggregatedOutput)||"";'
    'if(!n||n.status!=="completed"||n.exitCode!==0||'
    '!/(?:^|\\s)(?:\\/[^\\s]+\\/)?codex-gallery\\s+(?:faces|semantic)(?:\\s|$)/u.test(t))'
    'return null;let s=null;for(const a of i.trim().split(/\\r?\\n/u).reverse()){'
    'const c=a.trim();if(!c.startsWith("{")||!c.endsWith("}"))continue;'
    'try{s=JSON.parse(c);break}catch{}}'
    'if(!s||s.schema!=="nemotron.gallery-result.v1"||s.verified!==!0||'
    '!s.render||s.render.type!=="verified-local-image-grid"||s.render.verified!==!0||'
    '!Array.isArray(s.render.images)||s.render.images.length>250)return null;'
    'const a=[];for(const c of s.render.images){const o=c&&c.path,u=c&&c.mimeType;'
    'if(!c||c.verified!==!0||!Number.isSafeInteger(c.mediaId)||c.mediaId<1||'
    'typeof o!=="string"||!o.startsWith("/storage/emulated/0/")||o.includes("\\0")||'
    'typeof u!=="string"||!/^image\\/(?:avif|bmp|gif|jpeg|png|webp)$/u.test(u))return null;'
    'a.push({url:`/codex-local-image?path=${encodeURIComponent(o)}`,'
    'label:typeof c.label==="string"&&c.label.trim()?c.label.trim():"Verified gallery image"});}'
    'return{images:a,message:typeof s.displayMessage==="string"&&s.displayMessage.trim()?'
    's.displayMessage.trim():`Found ${a.length} verified gallery image(s).`,'
    'hasMore:s.hasMore===!0,nextOffset:Number.isSafeInteger(s.nextOffset)?s.nextOffset:null}}'
    'function O(e){return e.messageType==="commandExecution"&&!!e.commandExecution}'
)
BASE_THREAD_COMMAND_EXPANSION = (
    'function R(e){return O(e)?he.value.has(e.id)||!j.value.has(e.id)&&Rt(e):!1}'
)
PATCHED_THREAD_COMMAND_EXPANSION = (
    'function R(e){return O(e)?nemotronGalleryResult(e)!==null||he.value.has(e.id)||'
    '!j.value.has(e.id)&&Rt(e):!1}'
)
BASE_GROUPED_COMMAND_OUTPUT = (
    'd("div",Si,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(o)}]),'
    'textContent:h(((f=o.commandExecution)==null?void 0:f.aggregatedOutput)||"(no output)")},'
    'null,10,Ai)])'
)
PATCHED_GROUPED_COMMAND_OUTPUT = (
    'd("div",Si,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(o)}]),'
    'textContent:h(((f=o.commandExecution)==null?void 0:f.aggregatedOutput)||"(no output)")},'
    'null,10,Ai),nemotronGalleryResult(o)?(r(),l("section",{key:0,class:"nemotron-gallery-result",'
    '"data-gallery-schema":"nemotron.gallery-result.v1"},['
    'd("p",{class:"nemotron-gallery-status",role:"status","aria-live":"polite"},'
    'h(nemotronGalleryResult(o).message),1),d("ul",{class:"message-image-list '
    'message-generated-image-list nemotron-gallery-image-list"},[(r(!0),l(_,null,b(nemotronGalleryResult(o).images,m=>'
    '(r(),l("li",{key:m.url,class:"message-image-item"},[d("button",{class:'
    '"message-image-button",type:"button",title:m.label,onClick:k=>An(m.url)},'
    '[d("img",{class:"message-image-preview message-generated-image-preview",src:m.url,alt:m.label,loading:"lazy"},'
    'null,8,oo)],8,io)]))),128))]),nemotronGalleryResult(o).hasMore?'
    '(r(),l("p",{key:0,class:"nemotron-gallery-continuation"},'
    'h(`More gallery images remain. The next verified scan starts at offset '
    '${nemotronGalleryResult(o).nextOffset}.`),1)):y("",!0)])):y("",!0)])'
)
BASE_SINGLE_COMMAND_OUTPUT = (
    'd("div",Oi,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(t)}]),'
    'textContent:h(((s=t.commandExecution)==null?void 0:s.aggregatedOutput)||"(no output)")},'
    'null,10,Ri)])'
)
PATCHED_SINGLE_COMMAND_OUTPUT = (
    'd("div",Oi,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(t)}]),'
    'textContent:h(((s=t.commandExecution)==null?void 0:s.aggregatedOutput)||"(no output)")},'
    'null,10,Ri),nemotronGalleryResult(t)?(r(),l("section",{key:0,class:"nemotron-gallery-result",'
    '"data-gallery-schema":"nemotron.gallery-result.v1"},['
    'd("p",{class:"nemotron-gallery-status",role:"status","aria-live":"polite"},'
    'h(nemotronGalleryResult(t).message),1),d("ul",{class:"message-image-list '
    'message-generated-image-list nemotron-gallery-image-list"},[(r(!0),l(_,null,b(nemotronGalleryResult(t).images,o=>'
    '(r(),l("li",{key:o.url,class:"message-image-item"},[d("button",{class:'
    '"message-image-button",type:"button",title:o.label,onClick:u=>An(o.url)},'
    '[d("img",{class:"message-image-preview message-generated-image-preview",src:o.url,alt:o.label,loading:"lazy"},'
    'null,8,oo)],8,io)]))),128))]),nemotronGalleryResult(t).hasMore?'
    '(r(),l("p",{key:0,class:"nemotron-gallery-continuation"},'
    'h(`More gallery images remain. The next verified scan starts at offset '
    '${nemotronGalleryResult(t).nextOffset}.`),1)):y("",!0)])):y("",!0)])'
)
BASE_WORKED_COMMAND_OUTPUT = (
    'd("div",bo,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(o)}]),'
    'textContent:h(((f=o.commandExecution)==null?void 0:f.aggregatedOutput)||"(no output)")},'
    'null,10,xo)])'
)
PATCHED_WORKED_COMMAND_OUTPUT = (
    'd("div",bo,[d("pre",{class:C(["cmd-output",{"cmd-output-condensed":lt(o)}]),'
    'textContent:h(((f=o.commandExecution)==null?void 0:f.aggregatedOutput)||"(no output)")},'
    'null,10,xo),nemotronGalleryResult(o)?(r(),l("section",{key:0,class:"nemotron-gallery-result",'
    '"data-gallery-schema":"nemotron.gallery-result.v1"},['
    'd("p",{class:"nemotron-gallery-status",role:"status","aria-live":"polite"},'
    'h(nemotronGalleryResult(o).message),1),d("ul",{class:"message-image-list '
    'message-generated-image-list nemotron-gallery-image-list"},[(r(!0),l(_,null,b(nemotronGalleryResult(o).images,m=>'
    '(r(),l("li",{key:m.url,class:"message-image-item"},[d("button",{class:'
    '"message-image-button",type:"button",title:m.label,onClick:k=>An(m.url)},'
    '[d("img",{class:"message-image-preview message-generated-image-preview",src:m.url,alt:m.label,loading:"lazy"},'
    'null,8,oo)],8,io)]))),128))]),nemotronGalleryResult(o).hasMore?'
    '(r(),l("p",{key:0,class:"nemotron-gallery-continuation"},'
    'h(`More gallery images remain. The next verified scan starts at offset '
    '${nemotronGalleryResult(o).nextOffset}.`),1)):y("",!0)])):y("",!0)])'
)
THREAD_PATCHES = (
    ("English grouped command summary", BASE_THREAD_COMMAND_SUMMARY, PATCHED_THREAD_COMMAND_SUMMARY),
    ("accessible grouped command live status", BASE_THREAD_STATUS_SPAN, PATCHED_THREAD_STATUS_SPAN),
    ("verified gallery result parser", BASE_THREAD_COMMAND_TYPE, PATCHED_THREAD_COMMAND_TYPE),
    ("automatic verified gallery expansion", BASE_THREAD_COMMAND_EXPANSION, PATCHED_THREAD_COMMAND_EXPANSION),
    ("verified grouped gallery images", BASE_GROUPED_COMMAND_OUTPUT, PATCHED_GROUPED_COMMAND_OUTPUT),
    ("verified single gallery images", BASE_SINGLE_COMMAND_OUTPUT, PATCHED_SINGLE_COMMAND_OUTPUT),
    ("verified worked gallery images", BASE_WORKED_COMMAND_OUTPUT, PATCHED_WORKED_COMMAND_OUTPUT),
)

PATCHES = (
    ("max effort option", BASE_EFFORTS, PATCHED_EFFORTS),
    ("model selection event", BASE_MODEL_HANDLER, PATCHED_MODEL_HANDLER),
    ("effort selection event", BASE_EFFORT_HANDLER, PATCHED_EFFORT_HANDLER),
    ("cleanup convergence handler", BASE_CLEANUP_HANDLER, PATCHED_CLEANUP_HANDLER),
    ("cleanup convergence mount", BASE_CLEANUP_MOUNT, PATCHED_CLEANUP_MOUNT),
    ("cleanup convergence unmount", BASE_CLEANUP_UNMOUNT, PATCHED_CLEANUP_UNMOUNT),
    ("null-safe WebView sibling lookup", BASE_NULL_UNSAFE_NEXT_SIBLING, PATCHED_NULL_SAFE_NEXT_SIBLING),
    ("null-safe WebView parent lookup", BASE_NULL_UNSAFE_PARENT_NODE, PATCHED_NULL_SAFE_PARENT_NODE),
    ("null-safe WebView node removal", BASE_NULL_UNSAFE_REMOVE, PATCHED_NULL_SAFE_REMOVE),
    ("idempotent Vue application boot", BASE_APP_BOOT, PATCHED_APP_BOOT),
    ("English command activity", BASE_COMMAND_ACTIVITY, PATCHED_COMMAND_ACTIVITY),
    ("English command output activity", BASE_COMMAND_DELTA_ACTIVITY, PATCHED_COMMAND_DELTA_ACTIVITY),
    ("English secondary command activity", BASE_SECONDARY_COMMAND_ACTIVITY, PATCHED_SECONDARY_COMMAND_ACTIVITY),
)


def atomic_write(path, payload):
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = ASSET.read_text(encoding="utf-8")
    updated = source
    thread_source = THREAD_ASSET.read_text(encoding="utf-8")
    thread_updated = thread_source
    applied = []
    legacy_gallery_parser = PATCHED_THREAD_COMMAND_TYPE.replace(
        '!/(?:^|\\s)(?:\\/[^\\s]+\\/)?codex-gallery',
        '!/(?:^|[\\s"\\\'])(?:\\/[^\\s"\\\']+\\/)?codex-gallery',
        1,
    )
    if legacy_gallery_parser in thread_updated and PATCHED_THREAD_COMMAND_TYPE not in thread_updated:
        thread_updated = thread_updated.replace(
            legacy_gallery_parser, PATCHED_THREAD_COMMAND_TYPE, 1,
        )
        applied.append("repair gallery command matcher")
    legacy_gallery_list = 'class:"message-image-list nemotron-gallery-image-list"'
    current_gallery_list = (
        'class:"message-image-list message-generated-image-list nemotron-gallery-image-list"'
    )
    legacy_gallery_preview = 'class:"message-image-preview",src:'
    current_gallery_preview = (
        'class:"message-image-preview message-generated-image-preview",src:'
    )
    if legacy_gallery_list in thread_updated and current_gallery_list not in thread_updated:
        if thread_updated.count(legacy_gallery_list) != 3:
            raise SystemExit("Refusing ambiguous gallery list size migration")
        thread_updated = thread_updated.replace(legacy_gallery_list, current_gallery_list)
        applied.append("full-size gallery lists")
    gallery_preview_count = sum(
        thread_updated.count(f'{legacy_gallery_preview}{name}.url')
        for name in ("m", "o")
    )
    if gallery_preview_count and current_gallery_preview not in thread_updated:
        if gallery_preview_count != 3:
            raise SystemExit("Refusing ambiguous gallery preview size migration")
        for name in ("m", "o"):
            thread_updated = thread_updated.replace(
                f'{legacy_gallery_preview}{name}.url',
                f'{current_gallery_preview}{name}.url',
            )
        applied.append("full-size gallery previews")
    for previous, migration_label in (
        (LEGACY_CLEANUP_HANDLER, "cleanup convergence race hardening"),
        (BUGGY_STRICT_CLEANUP_HANDLER, "cleanup convergence strict declaration"),
    ):
        if previous in updated and PATCHED_CLEANUP_HANDLER not in updated:
            updated = updated.replace(previous, PATCHED_CLEANUP_HANDLER, 1)
            applied.append(migration_label)
    if LEGACY_NULL_SAFE_REMOVE in updated and PATCHED_NULL_SAFE_REMOVE not in updated:
        updated = updated.replace(LEGACY_NULL_SAFE_REMOVE, PATCHED_NULL_SAFE_REMOVE, 1)
        applied.append("diagnostic null-node removal stack")
    if LEGACY_NULL_SAFE_NEXT_SIBLING in updated and PATCHED_NULL_SAFE_NEXT_SIBLING not in updated:
        updated = updated.replace(LEGACY_NULL_SAFE_NEXT_SIBLING, PATCHED_NULL_SAFE_NEXT_SIBLING, 1)
        applied.append("diagnostic null-sibling stack")
    if LEGACY_NULL_SAFE_PARENT_NODE in updated and PATCHED_NULL_SAFE_PARENT_NODE not in updated:
        updated = updated.replace(LEGACY_NULL_SAFE_PARENT_NODE, PATCHED_NULL_SAFE_PARENT_NODE, 1)
        applied.append("diagnostic null-parent stack")
    for diagnostic, replacement, label in (
        (DIAGNOSTIC_NULL_SIBLING, PATCHED_NULL_SAFE_NEXT_SIBLING, "restore null-safe sibling lookup"),
        (DIAGNOSTIC_NULL_PARENT, PATCHED_NULL_SAFE_PARENT_NODE, "restore null-safe parent lookup"),
        (DIAGNOSTIC_NULL_REMOVE, PATCHED_NULL_SAFE_REMOVE, "restore null-safe node removal"),
    ):
        if diagnostic in updated and replacement not in updated:
            updated = updated.replace(diagnostic, replacement, 1)
            applied.append(label)
    for label, base, patched in PATCHES:
        patched_count = updated.count(patched)
        base_count = updated.count(base)
        if patched_count == 1:
            continue
        if args.check:
            raise SystemExit(f"CodexApp UI patch is missing or ambiguous: {label}")
        if patched_count or base_count != 1:
            raise SystemExit(f"Refusing ambiguous CodexApp UI patch: {label}")
        updated = updated.replace(base, patched, 1)
        applied.append(label)
    for label, base, patched in THREAD_PATCHES:
        patched_count = thread_updated.count(patched)
        base_count = thread_updated.count(base)
        if patched_count == 1:
            continue
        if args.check:
            raise SystemExit(f"CodexApp lazy UI patch is missing or ambiguous: {label}")
        if patched_count or base_count != 1:
            raise SystemExit(f"Refusing ambiguous CodexApp lazy UI patch: {label}")
        thread_updated = thread_updated.replace(base, patched, 1)
        applied.append(label)
    updated_bytes = updated.encode("utf-8")
    canonical_name = ASSET.name
    index_source = INDEX.read_text(encoding="utf-8")
    index_updated, replacements = FRONTEND_SCRIPT_RE.subn(
        f'src="/assets/{canonical_name}"', index_source, count=1,
    )
    if replacements != 1:
        raise SystemExit("Refusing ambiguous frontend module asset reference")
    index_updated, premount_overlay_count = PREMOUNT_OVERLAY_RE.subn("", index_updated)
    if args.check:
        if updated != source:
            raise SystemExit("CodexApp UI patch is not materialized in the canonical frontend asset")
        if thread_updated != thread_source:
            raise SystemExit("CodexApp lazy UI patch is not materialized in the canonical thread asset")
        if index_updated != index_source:
            raise SystemExit(f"Frontend index does not reference the canonical module entry: {canonical_name}")
        print(
            "CODEXAPP_UI_PATCH_OK max_effort=1 exact_selection_events=2 cleanup_convergence=1 "
            "idempotent_boot=1 english_progress=accessible module_graph=canonical "
            f"frontend_asset={canonical_name}"
        )
        return 0
    if updated != source:
        atomic_write(ASSET, updated_bytes)
    if thread_updated != thread_source:
        atomic_write(THREAD_ASSET, thread_updated.encode("utf-8"))
    if index_updated != index_source:
        atomic_write(INDEX, index_updated.encode("utf-8"))
        applied.append(
            "frontend post-mount boot" if premount_overlay_count else "canonical frontend module graph"
        )
    status = "APPLIED" if applied else "OK"
    suffix = f" changes={','.join(applied)}" if applied else ""
    print(
        f"CODEXAPP_UI_PATCH_{status} max_effort=1 exact_selection_events=2 cleanup_convergence=1 "
        f"idempotent_boot=1 english_progress=accessible module_graph=canonical "
        f"frontend_asset={canonical_name}{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
