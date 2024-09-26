Feature: While building a flo

  Scenario Outline: Flo Name Validation
     When use the name, <flo_name>
     Then it should be <validity>

  Examples: Flo Names
   | flo_name        | validity |
   | CorrectName     | True     |
   | Wrong Name      | False    |
   | correct_name    | True     |
   | correct-name    | True     |
   | wrong/name      | False    |