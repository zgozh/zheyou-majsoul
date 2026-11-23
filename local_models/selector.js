const ZheyouLocalApiUrl = "http://127.0.0.1:25034";
const ZheyouLocalKey = "zheyou-local-inference";

function zheyouLocalApi(command, payload) {
    if (command === "check_for_update") return Promise.resolve(null);
    if (command === "apply_update") throw new Error("请从择优雀魂发布页下载更新。");
    if (command.startsWith("native_api_")) {
        if (!["native_api_models", "native_api_health", "native_api_key_status"].includes(command)) {
            throw new Error("本版本仅支持本地推理。");
        }
        payload = {...payload, baseUrl: ZheyouLocalApiUrl, key: ZheyouLocalKey, proxy: ""};
    }
    if (command === "update_config" && payload?.newConfig?.bot?.api) {
        const api = payload.newConfig.bot.api;
        const base = api.base_url === ZheyouLocalApiUrl + "/" ? api.base_url : ZheyouLocalApiUrl;
        payload = {...payload, newConfig: {...payload.newConfig, bot: {...payload.newConfig.bot,
            api: {...api, base_url: base, key: ZheyouLocalKey, proxy: "", proxy_enabled: false}}}};
    }
    if (command === "open_external_url" && /shinkuan|discord\.gg/.test(payload?.url ?? "")) {
        payload = {...payload, url: "https://github.com/zgozh/zheyou-majsoul"};
    }
    return V(command, payload);
}

function ZheyouUsesLocalApi(api) {
    return api?.enabled && api.base_url.trim().replace(/\/+$/, "") === ZheyouLocalApiUrl;
}

function ZheyouLocalModelSelector() {
    const config = aT(state => state.config);
    const [open, setOpen] = S.useState(false);
    const [busy, setBusy] = S.useState(false);
    const [error, setError] = S.useState("");
    const [available, setAvailable] = S.useState(null);
    const usingLocal = ZheyouUsesLocalApi(config?.bot?.api);
    S.useEffect(() => {
        if (!usingLocal) return;
        let active = true;
        const refresh = () => Y("native_api_models", {}).then(items => {
            if (active) setAvailable(items.map(item => item.id));
        }, () => { if (active) setAvailable([]); });
        void refresh();
        const interval = setInterval(refresh, 2500);
        return () => { active = false; clearInterval(interval); };
    }, [usingLocal]);
    if (!config) return null;

    const baseUrl = ZheyouLocalApiUrl;
    const key = ZheyouLocalKey;
    const api = config.bot.api;
    const selected = {
        "3p": usingLocal && api.model_3p === "epsilon-prism-3p" ? api.model_3p : "native-3p",
        "4p": usingLocal && api.model_4p === "mortal-s42" ? api.model_4p : "native-4p",
    };
    const ready = available && Object.values(selected).every(model => available.includes(model));

    async function select(mode, model) {
        const models = {...selected, [mode]: model};
        const enabled = Object.values(models).some(value => !value.startsWith("native-"));
        setError("");
        setBusy(true);
        try {
            if (!model.startsWith("native-")) {
                const available = await Y("native_api_models", {baseUrl, key, proxy: ""});
                if (!available.some(item => item.id === model)) {
                    throw new Error("模型还在加载或启动失败，详见 logs/local-models.log");
                }
            }
            if (enabled) {
                await LD({...api, enabled, base_url: baseUrl, key, proxy_enabled: false,
                    model_3p: models["3p"], model_4p: models["4p"]});
            } else {
                await LD({...api, enabled: false, model_3p: "", model_4p: ""});
            }
        } catch (failure) {
            setError(String(failure));
        } finally {
            setBusy(false);
        }
    }

    function field(mode, label, model, modelLabel) {
        return G.jsxs("label", {className: "grid gap-1.5 text-sm", children: [
            label,
            G.jsxs("select", {className: "rounded-md border border-border bg-background px-2 py-1.5",
                "aria-label": label, "data-model-mode": mode, disabled: busy, value: selected[mode],
                onChange: event => void select(mode, event.target.value), children: [
                    G.jsx("option", {value: "native-" + mode, children: "Native（内置）"}),
                    G.jsx("option", {value: model, children: modelLabel}),
                ]}),
        ]});
    }

    return G.jsxs(G.Fragment, {children: [
        G.jsx("button", {type: "button", "data-local-model-selector": "", onClick: () => setOpen(true),
            className: "rounded-md border border-border px-2 text-[11px] leading-5",
            children: usingLocal ? ready ? "模型 · 本地" : "模型 · 准备中" : "模型"}),
        open && G.jsx(uT, {open: true, onOpenChange: value => !busy && setOpen(value),
            children: G.jsxs(mT, {className: "sm:max-w-md", children: [
                G.jsxs(hT, {children: [
                    G.jsx(_T, {children: "对局模型"}),
                    G.jsx("p", {className: "text-sm text-muted-foreground", children: "按牌桌人数选择，切换后自动保存。"}),
                ]}),
                field("3p", "三麻", "epsilon-prism-3p", "Epsilon-Prism 3P"),
                field("4p", "四麻", "mortal-s42", "Mortal-S42"),
                error && G.jsx("p", {role: "alert", className: "break-words text-sm text-red-500", children: error}),
            ]}),
        }),
    ]});
}

function ZheyouLocalReconnect() {
    const api = aT(state => state.config?.bot?.api);
    const players = nE(state => state.game?.num_players);
    const [busy, setBusy] = S.useState(false);
    const [message, setMessage] = S.useState("");
    if (!ZheyouUsesLocalApi(api)) return null;

    async function retry() {
        setBusy(true);
        setMessage("");
        try {
            // Zheyou compares the stored URL to rebuild its inference client.
            // Both URL forms reach the same loopback service after normalization.
            const baseUrl = api.base_url.trim() === ZheyouLocalApiUrl ? ZheyouLocalApiUrl + "/" : ZheyouLocalApiUrl;
            const models = await Y("native_api_models", {baseUrl, proxy: api.proxy_enabled ? api.proxy : "", key: api.key});
            const active = players === 3 ? api.model_3p : players === 4 ? api.model_4p : "";
            const required = active ? [active] : [api.model_3p, api.model_4p].filter(Boolean);
            if (required.some(id => !models.some(model => model.id === id))) {
                setMessage("中转可达，所选模型还未就绪。可稍后再试或查看本地模型日志。");
                return;
            }
            if (aT.getState().config?.bot?.api !== api) {
                setMessage("模型设置已变化，请按当前设置重连。");
                return;
            }
            await LD({...api, base_url: baseUrl});
            setMessage("中转可达，下次需要模型决策时将重试。");
        } catch {
            setMessage("重连失败。请查看日志，必要时关闭窗口后重新打开 EXE。");
        } finally {
            setBusy(false);
        }
    }

    return G.jsxs("div", {className: "grid gap-1", children: [
        G.jsx("button", {type: "button", "data-local-inference-reconnect": "", onClick: retry, disabled: busy,
            className: "w-fit rounded-md border border-border px-2 py-1 text-xs",
            children: busy ? "正在检查…" : "重连本地推理"}),
        message && G.jsx("p", {role: "status", "data-local-reconnect-status": "",
            className: "text-xs leading-relaxed text-muted-foreground", children: message}),
    ]});
}

function ZheyouInferenceWarning() {
    return G.jsx("span", {className: "shrink-0 rounded bg-amber-500/20 px-1.5 py-0.5 text-[11px] text-amber-500",
        title: "本地推理请求失败，当前使用内置模型。", children: "本地推理异常 · 已回退"});
}
