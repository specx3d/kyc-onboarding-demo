# Fictional Sanctions Screening Procedure (demo)

This is an invented procedure for a prototype. It is not a legal or regulatory text.

## §1 Scope
Every onboarding customer is screened against the sanctions watchlist after document verification. Each potential match (hit) must be handled under this procedure.

## §2 Name similarity thresholds
Names are compared after normalisation (upper case, no diacritics, token order ignored). A name score of 85 or more is a potential match. A score from 80 to 84 is a weak match that must be reviewed. Below 80 no hit is raised.

## §3 Date of birth
A full date of birth that equals the watchlist date of birth strengthens the match. A watchlist entry that has only a year matches when the year is equal. If both dates are known and differ (different day, month or year), the date of birth counts against the match. If a date is unknown on either side, it neither supports nor weakens the match.

## §4 Nationality
Nationality is a secondary indicator. A different nationality can support closing a hit as false positive only together with a different date of birth (§6). It can never close a hit on its own.

## §5 Aliases and transliteration
Aliases on the watchlist are compared with the same rules as the primary name. Transliteration variants (for example W/V, Ł/L, Ü/UE) are expected and must not be treated as differences in identity.

## §6 Closing as false positive
A hit may be recommended as a false positive only if the date of birth of the customer and of the watchlist entry are both known and different. A different nationality supports this view. Without a known, different date of birth, a hit must be reviewed by an analyst.

## §7 Mandatory escalation
A hit must be escalated and never closed automatically when: (a) the name score is 85 or more and the date of birth is an exact match; (b) the name score is 85 or more and the watchlist year equals the customer year; (c) the normalised name is identical and the date of birth is unknown on either side.

## §8 Human decision and documentation
No hit is closed by a system or by an AI model. An AI recommendation is advisory only. A human analyst must record the decision (approve, reject or escalate) with a written comment. The record must contain who decided, when, the AI recommendation and its cited sections, and the model versions used.
