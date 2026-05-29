# 주식 시그널 대쉬보드

애널리스트 리포트 + 섹터 자금 흐름으로 종목을 선별하는 Streamlit 멀티페이지 대쉬보드.

## 페이지
- **⚡ 애널리스트 시그널**: 선행 시그널, 핫 섹터, 목표가 추이 분석
- **🏭 섹터 성장 대쉬보드**: 섹터 ETF 자금 유입, 덜 오른 종목 찾기

## 로컬 실행
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Community Cloud 배포

1. **GitHub 저장소 생성** 후 이 폴더(`stock-dashboard`) 전체를 업로드
   - `data/reports.db` 포함 (크롤링된 리포트 데이터, 약 5MB)
2. https://share.streamlit.io 접속 → GitHub 계정 연결
3. **New app** → 저장소 선택 → Main file: `streamlit_app.py`
4. Deploy 클릭 → 몇 분 후 공개 URL 발급

### 배포 환경 주의사항
- **크롤링 버튼**: 클라우드에서는 네이버가 데이터센터 IP를 차단할 수 있어 동작이 불안정합니다. 데이터 갱신은 로컬에서 크롤링 후 `data/reports.db`를 다시 커밋하는 방식 권장.
- **관심종목(watchlist.json)**: 클라우드 파일시스템은 휘발성이라 앱 재시작 시 초기화됩니다. 영구 보관이 필요하면 추후 외부 저장소(예: Google Sheets, DB) 연동 필요.
- **섹터 ETF/주가/투자자 데이터**: 네이버 차트 API는 클라우드에서도 대체로 동작하나, 차단 시 캐시(`@st.cache_data`)로 완화됩니다.

## 데이터 갱신 (로컬)
애널리스트 시그널 페이지 사이드바의 "📡 네이버 크롤링 시작" 버튼으로 `data/reports.db` 갱신.
업종 정보 갱신은 `signal_lib`의 종목별 sector 업데이트 스크립트 활용.
