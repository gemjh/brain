import argparse
import os
import re
import wave
from typing import Iterator, Optional, Tuple

from sqlalchemy import text

from api.database import SessionLocal

AUDIO_EXTS = {".wav", ".m4a", ".mp4", ".aac"}
QUESTION_RE = re.compile(r"^p_(\d+)(?:_(\d+))?$")


def parse_question_numbers(filename: str) -> Optional[Tuple[int, int]]:
    base = os.path.splitext(filename)[0]
    match = QUESTION_RE.match(base)
    if not match:
        return None
    question_no = int(match.group(1))
    question_minor_no = int(match.group(2) or 0)
    return question_no, question_minor_no


def get_wav_info(path: str) -> Tuple[float, int]:
    with wave.open(path, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        duration = frames / float(rate) if rate else 0.0
        return duration, rate


def iter_audio_files(root_dir: str) -> Iterator[Tuple[str, str, str]]:
    for assess_type in os.listdir(root_dir):
        assess_path = os.path.join(root_dir, assess_type)
        if not os.path.isdir(assess_path):
            continue
        for question_cd in os.listdir(assess_path):
            question_path = os.path.join(assess_path, question_cd)
            if not os.path.isdir(question_path):
                continue
            for filename in os.listdir(question_path):
                file_path = os.path.join(question_path, filename)
                if not os.path.isfile(file_path):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in AUDIO_EXTS:
                    continue
                yield assess_type, question_cd, file_path


def get_next_order_num(db, patient_id: str) -> int:
    query = text(
        """
        SELECT IFNULL(MAX(order_num) + 1, 1)
        FROM SCORE
        WHERE PN = :patient_id
        """
    )
    return int(db.execute(query, {"patient_id": patient_id}).scalar() or 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Android folder audio files into assess_file_lst."
    )
    parser.add_argument("--root", required=True, help="Android root folder path")
    parser.add_argument("--patient-id", required=True, help="PATIENT_ID")
    parser.add_argument(
        "--order-num",
        type=int,
        default=None,
        help="ORDER_NUM (omit to auto-pick next order)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only and print what would be inserted",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        raise SystemExit(f"Root folder not found: {args.root}")

    db = SessionLocal()
    try:
        order_num = args.order_num
        if order_num is None:
            order_num = get_next_order_num(db, args.patient_id)

        insert_query = text(
            """
            INSERT INTO assess_file_lst (
                PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD,
                QUESTION_NO, QUESTION_MINOR_NO, FILE_NAME,
                DURATION, RATE, FILE_CONTENT
            ) VALUES (
                :patient_id, :order_num, :assess_type, :question_cd,
                :question_no, :question_minor_no, :file_name,
                :duration, :rate, :file_content
            )
            ON DUPLICATE KEY UPDATE
                FILE_NAME = VALUES(FILE_NAME),
                DURATION = VALUES(DURATION),
                RATE = VALUES(RATE),
                FILE_CONTENT = VALUES(FILE_CONTENT),
                UPDATE_DATE = NOW()
            """
        )

        inserted = 0
        skipped = 0
        for assess_type, question_cd, file_path in iter_audio_files(args.root):
            filename = os.path.basename(file_path)
            numbers = parse_question_numbers(filename)
            if not numbers:
                skipped += 1
                continue
            question_no, question_minor_no = numbers

            duration = None
            rate = None
            if os.path.splitext(filename)[1].lower() == ".wav":
                duration, rate = get_wav_info(file_path)

            if args.dry_run:
                print(
                    f"[DRY] {assess_type}/{question_cd}/{filename} "
                    f"(q={question_no}, minor={question_minor_no})"
                )
                continue

            with open(file_path, "rb") as f:
                file_content = f.read()

            db.execute(
                insert_query,
                {
                    "patient_id": args.patient_id,
                    "order_num": order_num,
                    "assess_type": assess_type,
                    "question_cd": question_cd,
                    "question_no": question_no,
                    "question_minor_no": question_minor_no,
                    "file_name": filename,
                    "duration": duration,
                    "rate": rate,
                    "file_content": file_content,
                },
            )
            inserted += 1

        if not args.dry_run:
            db.commit()

        print(
            f"Completed. order_num={order_num}, inserted={inserted}, skipped={skipped}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
