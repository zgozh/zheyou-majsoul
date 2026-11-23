function ZheyouTileKind(tile) {
    if (typeof tile !== "string") return -1;
    const honor = "ESWNPFC".indexOf(tile);
    if (tile.length === 1 && honor >= 0) return 27 + honor;
    const suited = /^([0-9])([mps])(r?)$/.exec(tile);
    if (suited && (!suited[3] || suited[1] === "5")) {
        return "mps".indexOf(suited[2]) * 9 + (Number(suited[1]) || 5) - 1;
    }
    return -1;
}

function ZheyouKindName(kind) {
    return kind >= 27 ? "东南西北白发中"[kind - 27] : `${kind % 9 + 1}${"mps"[Math.floor(kind / 9)]}`;
}

function ZheyouShanten(hand, fixed) {
    let best = 8;
    function search(kind, sets, parts, pair) {
        while (kind < 34 && !hand[kind]) kind++;
        if (kind === 34) {
            best = Math.min(best, 8 - 2 * sets - Math.min(parts, 4 - sets) - pair);
            return;
        }
        const count = hand[kind];
        const suitRank = kind < 27 ? kind % 9 : 9;
        hand[kind]--;
        search(kind, sets, parts, pair);
        if (count >= 2) {
            hand[kind]--;
            if (!pair) search(kind, sets, parts, 1);
            if (sets + parts < 4) search(kind, sets, parts + 1, pair);
            if (count >= 3 && sets < 4) {
                hand[kind]--;
                search(kind, sets + 1, parts, pair);
                hand[kind]++;
            }
            hand[kind]++;
        }
        if (suitRank < 8 && hand[kind + 1]) {
            hand[kind + 1]--;
            if (sets + parts < 4) search(kind, sets, parts + 1, pair);
            if (suitRank < 7 && hand[kind + 2] && sets < 4) {
                hand[kind + 2]--;
                search(kind, sets + 1, parts, pair);
                hand[kind + 2]++;
            }
            hand[kind + 1]++;
        }
        if (suitRank < 7 && hand[kind + 2] && sets + parts < 4) {
            hand[kind + 2]--;
            search(kind, sets, parts + 1, pair);
            hand[kind + 2]++;
        }
        hand[kind]++;
    }
    search(0, fixed, 0, 0);
    if (fixed) return best;
    const orphans = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
    const distinctOrphans = orphans.filter(kind => hand[kind]).length;
    const pairs = hand.filter(count => count >= 2).length;
    const distinct = hand.filter(Boolean).length;
    return Math.min(best, 6 - pairs + Math.max(0, 7 - distinct),
        13 - distinctOrphans - Number(orphans.some(kind => hand[kind] >= 2)));
}

function ZheyouRecommendationPosition(events = [], seat) {
    const round = events[0];
    const initial = round?.tehais?.[seat];
    if (round?.type !== "start_kyoku" || !Array.isArray(initial) || initial.length !== 13) return null;
    const players = round.num_players ?? round.scores?.length;
    if (players !== 3 && players !== 4) return null;
    const hand = Array(34).fill(0);
    const visible = Array(34).fill(0);
    const rivers = Array.from({length: players}, () => new Set());
    const riichi = new Set();
    let fixed = 0;
    let valid = true;
    function record(tile, handChange, reveal) {
        const kind = ZheyouTileKind(tile);
        if (kind < 0) { valid = false; return; }
        hand[kind] += handChange;
        visible[kind] += Number(reveal);
        if (hand[kind] < 0 || visible[kind] > 4) valid = false;
    }
    initial.forEach(tile => record(tile, 1, true));
    record(round.dora_marker, 0, true);
    for (const event of events.slice(1)) {
        const own = event.actor === seat;
        if (event.type === "tsumo" && own) {
            record(event.pai, 1, true);
        } else if (event.type === "dahai") {
            record(event.pai, own ? -1 : 0, !own);
            rivers[event.actor]?.add(ZheyouTileKind(event.pai));
        } else if (["chi", "pon", "daiminkan", "ankan"].includes(event.type)) {
            const size = event.type === "daiminkan" ? 3 : event.type === "ankan" ? 4 : 2;
            if (event.consumed?.length !== size) return null;
            event.consumed.forEach(tile => record(tile, own ? -1 : 0, !own));
            if (own) fixed++;
        } else if (["kakan", "kita", "nukidora"].includes(event.type)) {
            record(event.type === "kakan" ? event.pai : "N", own ? -1 : 0, !own);
        } else if (event.type === "dora") {
            record(event.dora_marker, 0, true);
        } else if (event.type === "reach_accepted") {
            riichi.add(event.actor);
        }
        if (!valid || fixed > 4) return null;
    }
    return valid ? {players, hand, visible, fixed, rivers, riichi} : null;
}

function ZheyouDiscardShape(position, discard) {
    const {players, hand, visible, fixed} = position;
    if (discard < 0 || !hand[discard] || hand.reduce((sum, count) => sum + count, 0) + 3 * fixed !== 14) return null;
    hand[discard]--;
    const shanten = ZheyouShanten(hand, fixed);
    const tiles = [];
    let remaining = 0;
    for (let kind = 0; kind < 34; kind++) {
        if (visible[kind] >= 4 || (players === 3 && kind >= 1 && kind <= 7)) continue;
        hand[kind]++;
        if (ZheyouShanten(hand, fixed) < shanten) {
            tiles.push(ZheyouKindName(kind));
            remaining += 4 - visible[kind];
        }
        hand[kind]--;
    }
    hand[discard]++;
    return {shanten, tiles, remaining};
}

function ZheyouExplainRecommendation(response, first) {
    if (!first?.type) return "";
    const action = response.action ?? response.reaction ?? response;
    if (action.type && action.type !== first.type) return "";
    const tile = action.pai ?? first.pais?.[0];
    const discard = ZheyouTileKind(tile);
    if (first.type === "dahai" && first.pais?.length && ZheyouTileKind(first.pais[0]) !== discard) return "";
    const seat = response._recommendationSeat ?? action.actor;
    if (first.type === "dahai" || first.type === "reach") {
        const position = ZheyouRecommendationPosition(response._recommendationEvents, seat);
        const reach = first.type === "reach";
        const parts = [];
        if (position && discard >= 0) {
            if (!reach && position.riichi.has(seat)) return "自己已经立直。未选择和牌或允许的暗杠等操作时，通常只能打出刚摸到的牌。";
            const shape = ZheyouDiscardShape(position, discard);
            if (shape) {
                const distance = shape.shanten === 0 ? "听牌" : `${shape.shanten} 向听`;
                const examples = shape.tiles.slice(0, 5).join("、");
                const waits = shape.tiles.length ? `${shape.tiles.length > 5 ? "例如" : "为"}${examples}` : "";
                parts.push(`打出 ${tile} 后${distance}；${shape.shanten === 0 ? "和牌张" : "降低向听的进张"}${waits}，按可见牌最多还有 ${shape.remaining} 张。`);
                const draw = response._recommendationEvents.at(-1);
                if (!reach && draw.type === "tsumo" && draw.actor === seat && ZheyouTileKind(draw.pai) !== discard) {
                    const alternative = ZheyouDiscardShape(position, ZheyouTileKind(draw.pai));
                    if (alternative && alternative.shanten > shape.shanten) {
                        parts.push(`比直接摸切 ${draw.pai} 少 ${alternative.shanten - shape.shanten} 向听。`);
                    } else if (alternative?.shanten === shape.shanten && alternative.remaining < shape.remaining) {
                        parts.push(`与摸切 ${draw.pai} 的向听数相同，但多 ${shape.remaining - alternative.remaining} 张有效牌。`);
                    }
                }
            }
            const safe = [...position.riichi].filter(other => other !== seat && position.rivers[other]?.has(discard));
            if (!reach && safe.length) parts.push(`这张牌是${safe.map(other => `座位 ${other}`).join("、")}的现物，对其他玩家仍要看风险。`);
        }
        if (reach) parts.push("立直本身增加 1 翻，并有一发和里宝牌机会；同时要付 1000 点，之后基本不能改牌形。");
        return parts.join("") || "这巡缺少可核对的完整手牌，暂时无法判断打出后对牌形或防守的影响。";
    }
    switch (first.type) {
        case "chi": return "吃牌可把手里的两张牌与上家打出的牌组成顺子，凑好一组面子。代价是失去门清和立直资格，还需要确认副露后有役。";
        case "pon": {
            const round = response._recommendationEvents?.[0];
            const players = round?.num_players ?? round?.scores?.length;
            const seatWind = 27 + ((seat - round?.oya + players) % players);
            if (discard >= 31 || (discard >= 27 && (discard === seatWind || discard === ZheyouTileKind(round?.bakaze)))) {
                return `碰${ZheyouKindName(discard)}能组成役牌刻子，即使副露也有和牌役。代价是失去门清和立直机会。`;
            }
            return "碰牌可把对子变成一组刻子，加快做成面子的速度；同时会失去门清和立直机会，需要确认副露后的役。";
        }
        case "none": return "跳过可以保留手里的牌形。门清时还能保留立直机会，也避免因副露提前暴露牌形。";
        case "kita": return "拔北会把北计作拔北宝牌，并补摸一张牌；门清状态仍可保留。";
        case "ankan": return "暗杠能保留门清，并补摸一张岭上牌。新翻的杠宝牌也可能提高其他玩家的打点。";
        case "daiminkan": return "大明杠把刻子变成杠子，可补摸岭上牌并翻出杠宝牌。其他玩家也可能从新增宝牌受益。";
        case "kakan": return "加杠能补摸岭上牌并打开新宝牌，但其他玩家有机会抢杠和牌。";
        case "hora": return Number.isInteger(action.actor) && action.actor === action.target
            ? "手牌已满足自摸和牌条件，可以立即取得点数。" : "当前可以和牌，接受后即可按本次和牌结算。";
        case "ryukyoku": return "选择流局会结束这一小局，放弃继续摸打。是否划算取决于起手牌形和当时的比分。";
        default: return "";
    }
}

function zheyouModelMeta(meta) {
    const title = meta?.show?.title;
    if (!title?.startsWith("Akagi · ")) return meta;
    return {...meta, show: {...meta.show, title: "\u67d8\u682f" + title.slice(5)}};
}

function ZheyouRecommendationValue(response, value) {
    const title = response?.meta?.show?.title;
    return value && /^\u67d8\u682f · (epsilon-prism-3p|mortal-s42)$/.test(title) ? `偏好 ${value}` : value;
}

function ZheyouRecommendationNote({response, first}) {
    const explanation = S.useMemo(() => response ? ZheyouExplainRecommendation(response, first) : "", [response, first]);
    if (!explanation) return null;
    return G.jsxs("p", {className: "border-t border-border px-2 py-1.5 text-xs leading-relaxed text-muted-foreground",
        "data-recommendation-reason": "", children: [
            G.jsx("strong", {className: "font-semibold text-foreground", children: "局面解读　"}), explanation,
        ]});
}
