import os
import subprocess

# 프로젝트 루트 (stock-dashboard/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def is_git_repo() -> bool:
    return os.path.isdir(os.path.join(ROOT, ".git"))


def is_cloud() -> bool:
    """Streamlit Community Cloud 환경 여부.
    클라우드는 저장소를 /mount/src 경로에 마운트하고 Linux에서 실행됨."""
    path = os.path.abspath(__file__).replace("\\", "/")
    if path.startswith("/mount/"):
        return True
    if os.path.isdir("/mount/src"):
        return True
    return False


def is_local() -> bool:
    """로컬 PC에서 실행 중이고 git 푸시가 가능한 환경."""
    return is_git_repo() and not is_cloud()


def push_data_files(files: list, message: str = "데이터 갱신") -> tuple:
    """지정한 파일들을 커밋·푸시. (성공여부, 메시지) 반환.
    git 저장소가 아니거나(클라우드 등) 실패 시 조용히 False 반환."""
    if not is_git_repo():
        return False, "git 저장소가 아님 (클라우드 환경 — 자동 푸시 건너뜀)"

    try:
        def run(args):
            return subprocess.run(
                ["git"] + args, cwd=ROOT,
                capture_output=True, text=True, timeout=120,
            )

        add = run(["add"] + files)
        if add.returncode != 0:
            return False, f"git add 실패: {add.stderr.strip()}"

        diff = run(["diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return False, "변경된 데이터 없음 (커밋 생략)"

        commit = run(["-c", "user.email=ipobrief@gmail.com",
                      "-c", "user.name=ipobrief",
                      "commit", "-m", message])
        if commit.returncode != 0:
            return False, f"git commit 실패: {commit.stderr.strip()}"

        push = run(["push"])
        if push.returncode != 0:
            return False, f"git push 실패: {push.stderr.strip()}"

        return True, "GitHub에 푸시 완료 → 클라우드 자동 재배포됩니다"
    except Exception as e:
        return False, f"오류: {e}"


def push_data(message: str = "데이터 갱신: reports.db") -> tuple:
    """data/reports.db를 커밋·푸시."""
    return push_data_files(["data/reports.db"], message)
