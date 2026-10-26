# Adapted from abertsch72/oolong at 0bb7eabe839218fee7fe8d007f41cfc2fd3ae24c.
# Only imports and unrelated DnD helpers were removed. Function bodies are unchanged.
# See LICENSE.oolong for the upstream MIT license.
import ast
from datetime import datetime
import dateutil.parser

# try to parse the answer; super simple, idea is that we can go back and try harder on "low" or sometimes "med" confidence answers
def synth_attempt_answer_parse(answer):
    parse_confidence = "low"
    if ":" not in answer:  # bad start
        if len(answer) < 20:  # it's short, return the whole thing
            return answer, parse_confidence
        else:
            return answer.split()[-1], parse_confidence
    candidate_answer = answer.split(":")[-1].strip()
    candidate_answer = candidate_answer.replace(
        "*", ""
    )  # OpenAI models like bolding the answer


    candidate_answer = candidate_answer.replace(
        "[", ""
    ) 
    candidate_answer = candidate_answer.replace(
        "]", ""
    )  # Anthropic models like putting the answer in []
    parse_confidence = "med"
    if (
        "User:" in answer
        or "Answer:" in answer
        or "Date:" in answer
        or "Label" in answer
    ):
        parse_confidence = "high"
    if len(candidate_answer) < 20:
        parse_confidence = "vhigh"
    elif "more common" in candidate_answer:
        candidate_answer = "more common"
    elif "less common" in candidate_answer:
        candidate_answer = "less common"
    elif "same frequency" in candidate_answer:
        candidate_answer = "same frequency"

    return candidate_answer, parse_confidence


def synth_process_response(datapoint, output, model):

    score = 0
    gold = (
        ast.literal_eval(datapoint["answer"])[0]
        if "datetime" not in datapoint["answer"]
        else datetime.strptime(datapoint["answer"], "[datetime.date(%Y, %m, %d)]")
    )

    trimmed_output, parse_confidence =  synth_attempt_answer_parse(output)
    if str(trimmed_output) == str(gold):
        score = 1
    elif str(trimmed_output) in ['more common', 'less common', 'same frequency']: # account for these being slightly different wordings
        if str(trimmed_output) in  str(gold):
            score = 1
    elif (
        datapoint["answer_type"] == "ANSWER_TYPE.NUMERIC"
    ):  # partial credit for numbers
        try:
            trimmed_output = int(trimmed_output)
            gold = int(gold)
            score = 0.75 ** (abs(gold - trimmed_output))
        except Exception:
            parse_confidence = "low"  # didn't parse as a number, that's a bad sign
    elif datapoint["answer_type"] == "ANSWER_TYPE.DATE":
        try:
            trimmed_output = dateutil.parser.parse(trimmed_output)
            score = trimmed_output == gold
        except Exception:
            parse_confidence = "low"  # didn't parse as a date, that's a bad sign


    this_output = {
        "id": datapoint["id"],
        "context_window_id": datapoint["context_window_id"],
        "dataset": datapoint["dataset"],
        "model": model,
        "attempted_parse": str(trimmed_output),
        "parse_confidence": parse_confidence,
        "full_answer": output,
        "score": score,
        "answer": str(gold),
    }

    return this_output
