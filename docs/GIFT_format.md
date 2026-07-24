# General instructions

- At least one blank line must be left between each question.

- In the simple form, the question comes first, then the answers are set in between brackets, with an equal sign indicating the correct answer(s) and tilde the wrong answers. A Number sign will insert a response. Questions can be weighted by placing percentage signs around the weight. Comments are preceded by double slashes and are not imported.

## Useful GIFT Examples
Here are some useful GIFT examples that can be imported or used as rough templates. Many of these examples use questions from files as starting points.

**TIP:** Any GIFT file must be correctly encoded in UTF8. Beware of some Microsoft "fake" Unicode implementations which may cause strange characters to appear in your quizzes. When in doubt, save as a simple MS-DOS text file.

## Format Symbols
| Symbol | Use |
|---------|-----|
| // | Comment |
| ::Title:: | Title |
| ( | Start answer |
| ) | End answer |
| = | Correct answer |
| # | Answer comment |
| ~ | Wrong answer |
| -> | Match |
| %50% | Weight 50% |

## Format Symbols Explained
The multiple choice format below is shown as a comment line `//` for the question; when Moodle exports it, the question's unique ID number will appear here.

- The first `::` precedes the question title.
- The second `::` precedes the actual question.
- The first `{` indicates the start of answers.
- The correct answer is preceded by an `=` sign and wrong answers by a `~`.
- Teacher responses have a `#` in front of them.
- The question ends with a `}` and then a blank line.
- Note: it is `{ }`, not `( )`, parenthesis! These are usually obtained with help of the [AltGr] key.

### Example Format:
```plaintext
//Comment line 
::Question title 
:: Question {
=A correct answer
~Wrong answer1
#A response to wrong answer1
~Wrong answer2
#A response to wrong answer2
~Wrong answer3
#A response to wrong answer3
~Wrong answer4
#A response to wrong answer4
}
the shortest format for multiple choice:
e.g.,
Question{= A Correct Answer ~Wrong answer1 ~Wrong answer2 ~Wrong answer3 ~Wrong answer4 }
tip: If no question title is specified, the entire question will be used as the title during import into Moodle, which might add unnecessary words.
```

## Question Format Examples:
### Multiple Choice:
here is an acceptable simple GIFT multiple choice example:
```plaintext
to ask "Who's buried in Grant's tomb?":
gift format:
age: 1
grant's tomb?{=Grant ~no one ~Napoleon ~Churchill ~Mother Teresa }
details:
double slash comments can be added for explanations or context.
defaults include using titles like `::Grant's tomb::` for organization.
```
### True-False:
e.g.,
to ask if Grant was buried in NYC:
gift format:
declare true/false statement:
simple true-false example:
documentation on how to write questions with T/F options.
details about default behaviors regarding navigation and feedback messages within Moodle lessons.
defining feedback options including custom messages or hiding messages using non-breaking spaces (`&nbsp;`).
defining escape sequences for special characters (`{`, `}`, `=`, `#`, `~`) when used within questions such as TeX expressions or math formulas.
e.g., replacing `(T)` with `(=True)` and so forth after exporting from Word macros or spreadsheets tools like Excel or Open Office templates.`