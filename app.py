import streamlit as st
import json
import os
import re
import time
import asyncio
import tempfile
import edge_tts

# 페이지 기본 설정
st.set_page_config(page_title="CueSide - AI 연기 연습 파트너", page_icon="🎭", layout="centered")

# 내장 샘플 대본 데이터 (폴더 없이도 즉시 작동)
EMBEDDED_SAMPLES = {
    "bus_stop.json": {
        "scene_title": "버스 정류장 (현대극 2인극)",
        "characters": ["민수", "지은"],
        "lines": [
            {
                "speaker": "민수",
                "direction": "비가 내리는 버스 정류장. 젖은 우산을 접으며 차갑게 말한다.",
                "dialogue": "결국 올 줄 알았어. 근데 이제 와서 무슨 할 말이 남았니?",
                "emotion": "차갑고 실망한 톤"
            },
            {
                "speaker": "지은",
                "direction": "한숨을 쉬며 시선을 피한다",
                "dialogue": "미안해. 그땐 나도 어쩔 수가 없었어.",
                "emotion": "망설임/슬픔"
            },
            {
                "speaker": "민수",
                "direction": "헛웃음을 치며 고개를 돌린다",
                "dialogue": "어쩔 수 없었다는 말, 네 입버릇인 거 이제 지겹다.",
                "emotion": "분노/차갑게"
            },
            {
                "speaker": "지은",
                "direction": "민수의 소매를 조심스럽게 잡으며",
                "dialogue": "딱 5분만 내 얘기 들어주면 안 될까? 정말 마지막이야.",
                "emotion": "간절함/망설임"
            }
        ]
    },
    "romeo_juliet.json": {
        "scene_title": "로미오와 줄리엣 (발코니 씬)",
        "characters": ["로미오", "줄리엣"],
        "lines": [
            {
                "speaker": "로미오",
                "direction": "발코니 아래 정원에서 위를 올려다보며 속삭인다",
                "dialogue": "저기 창문을 통해 비치는 저 빛은 무엇인가? 저곳이 동쪽이고 줄리엣은 태양이로다.",
                "emotion": "설렘/차분함"
            },
            {
                "speaker": "줄리엣",
                "direction": "난간에 기대어 밤하늘을 보며 한숨짓는다",
                "dialogue": "오, 로미오, 로미오! 왜 당신은 로미오인가요?",
                "emotion": "망설임/슬픔"
            },
            {
                "speaker": "로미오",
                "direction": "조심스럽게 한 걸음 다가가며",
                "dialogue": "더 듣고 있을 것인가, 아니면 지금 대답을 할 것인가?",
                "emotion": "진지함/차분함"
            }
        ]
    }
}

# 세션 상태 초기화
if "step" not in st.session_state:
    st.session_state.step = "setup"
if "script_data" not in st.session_state:
    st.session_state.script_data = None
if "my_role" not in st.session_state:
    st.session_state.my_role = ""
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "blind_mode" not in st.session_state:
    st.session_state.blind_mode = False
if "show_hint" not in st.session_state:
    st.session_state.show_hint = False
if "results" not in st.session_state:
    st.session_state.results = []
if "turn_start_time" not in st.session_state:
    st.session_state.turn_start_time = None

# 샘플 대본 로드 (외부 파일 우선, 없으면 내장 데이터 사용)
def load_sample(filename):
    path = os.path.join("samples", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return EMBEDDED_SAMPLES[filename]

# 규칙 기반 + 간단 감정 태깅 대본 파서
def parse_raw_script(raw_text):
    lines = raw_text.strip().split("\n")
    parsed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]+)[:：]\s*(?:\(([^)]+)\)\s*)?(.*)$", line)
        if match:
            speaker = match.group(1).strip()
            direction = match.group(2).strip() if match.group(2) else ""
            dialogue = match.group(3).strip()
            emotion = "차분함"
            if any(k in direction + dialogue for k in ["화", "분노", "소리", "지겹", "짜증"]):
                emotion = "분노/차갑게"
            elif any(k in direction + dialogue for k in ["한숨", "미안", "슬픔", "눈물", "망설"]):
                emotion = "망설임/슬픔"
            elif any(k in direction + dialogue for k in ["웃", "기쁨", "반갑"]):
                emotion = "밝음"
            parsed.append({
                "speaker": speaker,
                "direction": direction,
                "dialogue": dialogue,
                "emotion": emotion
            })
    return parsed

# Edge-TTS 비동기 음성 생성 함수
async def generate_tts_async(text, emotion, output_path):
    voice = "ko-KR-InJoonNeural"
    rate = "+0%"
    pitch = "+0Hz"
    if "차갑" in emotion or "분노" in emotion:
        rate = "-5%"
        pitch = "-5Hz"
    elif "망설임" in emotion or "슬픔" in emotion:
        rate = "-12%"
        pitch = "-3Hz"
    elif "밝음" in emotion:
        rate = "+8%"
        pitch = "+4Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def get_tts_audio(text, emotion):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        temp_path = fp.name
    asyncio.run(generate_tts_async(text, emotion, temp_path))
    with open(temp_path, "rb") as f:
        audio_bytes = f.read()
    os.remove(temp_path)
    return audio_bytes

# 블라인드 텍스트 변환
def mask_dialogue(text):
    words = text.split()
    masked = []
    for w in words:
        if len(w) > 1:
            masked.append(w[0] + "█" * (len(w) - 1))
        else:
            masked.append(w)
    return " ".join(masked)

# Levenshtein 편집 거리 기반 유사도 계산
def calculate_accuracy(target, spoken):
    t = re.sub(r"[^가-힣a-zA-Z0-9]", "", target)
    s = re.sub(r"[^가-힣a-zA-Z0-9]", "", spoken)
    if not t:
        return 100.0
    if not s:
        return 0.0
    dp = [[0] * (len(s) + 1) for _ in range(len(t) + 1)]
    for i in range(len(t) + 1):
        dp[i][0] = i
    for j in range(len(s) + 1):
        dp[0][j] = j
    for i in range(1, len(t) + 1):
        for j in range(1, len(s) + 1):
            cost = 0 if t[i - 1] == s[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    dist = dp[len(t)][len(s)]
    acc = max(0.0, (1 - dist / max(len(t), len(s))) * 100)
    return round(acc, 1)

# --- UI 렌더링 ---
st.title("🎭 CueSide (큐사이드)")
st.caption("연극·영화 배우를 위한 AI 상대역 및 대본 분석 파트너 (MVP 데모)")

# 1. 설정 화면
if st.session_state.step == "setup":
    st.subheader("1단계: 연습할 대본 선택 또는 입력")
    mode = st.radio("대본 불러오기 방식", ["샘플 대본으로 체험하기 (추천)", "내 대본 직접 입력하기"], horizontal=True)

    if mode == "샘플 대본으로 체험하기 (추천)":
        sample_choice = st.selectbox("샘플 대본 선택", ["버스 정류장 (현대극 2인극)", "로미오와 줄리엣 (고전극 발췌)"])
        filename = "bus_stop.json" if "버스 정류장" in sample_choice else "romeo_juliet.json"
        data = load_sample(filename)
        st.info(f"**장면:** {data['scene_title']} | **등장인물:** {', '.join(data['characters'])}")
        
        with st.expander("대본 미리보기"):
            for item in data["lines"]:
                dir_txt = f"({item['direction']}) " if item["direction"] else ""
                st.write(f"**{item['speaker']}**: {dir_txt}\"{item['dialogue']}\" `[{item['emotion']}]`")

        my_role = st.selectbox("내가 연기할 배역을 선택하세요", data["characters"])
        if st.button("🎬 리허설 시작하기", type="primary", use_container_width=True):
            st.session_state.script_data = data
            st.session_state.my_role = my_role
            st.session_state.current_idx = 0
            st.session_state.results = []
            st.session_state.turn_start_time = time.time()
            st.session_state.step = "rehearsal"
            st.rerun()

    else:
        raw_input = st.text_area(
            "대본을 붙여넣으세요 (형식: 배역: (지문) 대사)",
            height=180,
            value='민수: (젖은 우산을 접으며 차갑게) 결국 올 줄 알았어. 근데 이제 와서 무슨 할 말이 남았니?\n지은: (한숨을 쉬며 시선을 피한다) 미안해. 그땐 나도 어쩔 수가 없었어.\n민수: 어쩔 수 없었다는 말, 네 입버릇인 거 이제 지겹다.'
        )
        parsed_lines = parse_raw_script(raw_input)
        if not parsed_lines:
            st.warning("⚠️ 화자를 구분할 수 없습니다. '배역: 대사' 형식으로 입력해 주세요.")
        else:
            chars = list(dict.fromkeys([x["speaker"] for x in parsed_lines]))
            my_role = st.selectbox("내가 연기할 배역 선택", chars)
            if st.button("🎬 입력한 대본으로 리허설 시작", type="primary", use_container_width=True):
                st.session_state.script_data = {
                    "scene_title": "사용자 입력 대본",
                    "characters": chars,
                    "lines": parsed_lines
                }
                st.session_state.my_role = my_role
                st.session_state.current_idx = 0
                st.session_state.results = []
                st.session_state.turn_start_time = time.time()
                st.session_state.step = "rehearsal"
                st.rerun()

# 2. 리허설 진행 화면
elif st.session_state.step == "rehearsal":
    data = st.session_state.script_data
    lines = data["lines"]
    idx = st.session_state.current_idx

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ 나가기"):
            st.session_state.step = "setup"
            st.rerun()
    with col2:
        st.markdown(f"<div style='text-align:center;'><b>{data['scene_title']}</b> (내 역할: {st.session_state.my_role})</div>", unsafe_allow_html=True)
    with col3:
        st.session_state.blind_mode = st.toggle("블라인드 모드", value=st.session_state.blind_mode)

    st.progress((idx) / len(lines))

    if idx < len(lines):
        current_line = lines[idx]
        is_my_turn = (current_line["speaker"] == st.session_state.my_role)

        st.divider()
        if idx > 0:
            prev = lines[idx - 1]
            st.caption(f"이전 대사 — {prev['speaker']}: \"{prev['dialogue']}\"")

        # 상대역 차례일 때
        if not is_my_turn:
            st.subheader(f"🗣️ [상대역: {current_line['speaker']}]")
            st.caption(f"감정 태그: `{current_line['emotion']}` | 지문: {current_line['direction'] or '없음'}")
            st.info(f"### \"{current_line['dialogue']}\"")

            try:
                audio_bytes = get_tts_audio(current_line["dialogue"], current_line["emotion"])
                st.audio(audio_bytes, format="audio/mp3", autoplay=True)
            except Exception as e:
                st.warning(f"음성 합성 일시 지연 (텍스트 모드로 진행): {e}")

            if st.button("다음 차례로 넘어가기 ➔", type="primary", use_container_width=True):
                st.session_state.current_idx += 1
                st.session_state.turn_start_time = time.time()
                st.session_state.show_hint = False
                st.rerun()

        # 내 차례일 때
        else:
            st.subheader(f"🎭 [내 차례: {current_line['speaker']}]")
            if current_line["direction"]:
                st.warning(f"🎬 지문: ({current_line['direction']})")

            display_text = mask_dialogue(current_line["dialogue"]) if st.session_state.blind_mode else current_line["dialogue"]
            st.success(f"### \"{display_text}\"")

            if st.session_state.show_hint:
                hint_words = " ".join(current_line["dialogue"].split()[:2])
                st.toast(f"💡 힌트: \"{hint_words}...\"")
                st.info(f"💡 첫 두 단어 힌트: **{hint_words}...**")

            st.write("🎙️ 대사를 말하거나(마이크 녹음), 환경 제한 시 아래 텍스트로 발화를 시뮬레이션하세요.")
            audio_val = st.audio_input("마이크로 내 대사 녹음하기")
            spoken_sim = st.text_input("발화 인식 결과 (테스트용 직접 수정 가능)", value=current_line["dialogue"], key=f"input_{idx}")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("⏮ 이전 대사", use_container_width=True) and idx > 0:
                    st.session_state.current_idx -= 1
                    st.rerun()
            with c2:
                if st.button("💡 힌트 보기", use_container_width=True):
                    st.session_state.show_hint = True
                    st.rerun()
            with c3:
                if st.button("✅ 대사 완료", type="primary", use_container_width=True):
                    reaction_time = round(time.time() - (st.session_state.turn_start_time or time.time()), 1)
                    acc = calculate_accuracy(current_line["dialogue"], spoken_sim)
                    st.session_state.results.append({
                        "line_num": idx + 1,
                        "target": current_line["dialogue"],
                        "spoken": spoken_sim,
                        "direction": current_line["direction"],
                        "accuracy": acc,
                        "reaction_time": reaction_time
                    })
                    st.session_state.current_idx += 1
                    st.session_state.turn_start_time = time.time()
                    st.session_state.show_hint = False
                    st.rerun()
    else:
        st.session_state.step = "report"
        st.rerun()

# 3. 피드백 리포트 화면
elif st.session_state.step == "report":
    st.subheader("📊 리허설 완료 피드백 리포트")
    results = st.session_state.results

    if not results:
        st.info("연습한 내 대사가 없습니다.")
    else:
        avg_acc = round(sum(r["accuracy"] for r in results) / len(results), 1)
        avg_time = round(sum(r["reaction_time"] for r in results) / len(results), 1)

        m1, m2 = st.columns(2)
        m1.metric("평균 대사 정확도", f"{avg_acc}%")
        m2.metric("평균 큐(Cue) 반응 속도", f"{avg_time}초")

        st.divider()
        st.write("### 🔍 구간별 상세 분석 및 연기 인사이트")
        for r in results:
            with st.container(border=True):
                st.write(f"**[대사 #{r['line_num']}]** 정확도: `{r['accuracy']}%` | 반응 속도: `{r['reaction_time']}초`")
                st.write(f"- **원본 대사:** {r['target']}")
                st.write(f"- **인식 대사:** {r['spoken']}")
                if r["direction"] and r["reaction_time"] > 3.0:
                    st.caption(f"💡 연기 인사이트: 지문('{r['direction']}') 동작을 수행하느라 반응 간격이 길어졌습니다. 자연스러운 호흡인지 점검해 보세요.")
                elif r["accuracy"] < 90:
                    st.caption("💡 암기 체크: 일부 조사나 어미가 원본 대본과 다릅니다. 블라인드 모드로 다시 연습해 보세요.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔁 처음부터 다시 연습", use_container_width=True):
            st.session_state.current_idx = 0
            st.session_state.results = []
            st.session_state.step = "rehearsal"
            st.rerun()
    with col_b:
        if st.button("🏠 다른 대본 선택", type="primary", use_container_width=True):
            st.session_state.step = "setup"
            st.rerun()
