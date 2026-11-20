# Primary research: survey and interview guide

PID objective: *"Online survey of at least 40 dispatchers and small fleet owners, supported by a few
interviews, to confirm the need and the required features."*

This is a ready-to-use draft. Put it into Google Forms or Microsoft Forms, share it in dispatcher
Telegram groups and with colleagues, and aim for 50+ replies so 40 complete ones remain.
**Check WIUT's research ethics procedure before sending it** (participant information and consent,
no personal data you don't need, anonymous answers). Each question is tagged with the feature or
PID claim it tests, so the results map straight onto your requirements and evaluation chapters.

---

## Participant information (first page of the form)

> This survey is part of a final-year Business Information Systems project at Westminster
> International University in Tashkent. It asks about how you dispatch trucks and takes about
> 5 minutes. It is anonymous: do not include your name, company name or MC number. Taking part is
> voluntary and you can stop at any time. Answers are used only for this project and deleted after
> it is marked. By continuing, you agree to take part.
>
> ☐ I am 18 or older and agree to take part.

## Section A: About you

1. What is your role? *(Dispatcher / Owner-operator / Fleet owner / Other)*: segment
2. How many trucks do you dispatch? *(1 / 2–5 / 6–10 / 11+)*: PID target is 1–5
3. Where are you based? *(USA / Uzbekistan / Other)*: remote dispatch teams
4. Years of dispatching experience? *(<1 / 1–2 / 3–5 / 5+)*
5. Main equipment? *(Van / Reefer / Flatbed / Power only / Box truck / Mixed)*

## Section B: How you work today (the problem)

6. Which tools do you use to find loads? *(tick all: DAT / Truckstop / 123Loadboard / Broker emails / Neblo or similar AI tool / Other)*
7. Where do you keep records of booked loads? *(TMS software / Spreadsheet / Paper / Chat apps / Nothing)*: PID rationale
8. How do drivers send status updates and POD? *(WhatsApp / Telegram / Text / Phone calls / An app / Other)*: Telegram bot
9. How do you decide whether a load is worth taking? *(Rate per mile in my head / Calculator / Spreadsheet / Software tells me / Experience)*: decision engine
10. Do you include empty (deadhead) miles when you judge a rate? *(Always / Sometimes / Never)*: real rate per mile
11. About how many broker emails do you write per day? *(0–5 / 6–20 / 21–50 / 50+)*: AI email
12. About how many broker calls do you make per day? *(0–5 / 6–20 / 21–50 / 50+)*: Call Assistant
13. If you use a TMS, what do you pay per month? *(None / under $50 / $50–150 / $150+)*: cost gap
14. What is the most time-consuming part of your day? *(open text)*

## Section C: Feature value (rate each 1 = not useful, 5 = very useful)

15. Load search showing whether each load is profitable after deadhead (Accept / Negotiate / Reject)
16. An hours-of-service check before accepting a load
17. A suggested counter-offer rate and walk-away rate before calling a broker
18. AI that writes the email to the broker for you
19. Emailing several brokers at once with a personalised message
20. A broker directory with each broker's lanes and average rates
21. One-click booking that saves the load (no re-typing)
22. A status board of all loads (Available / Dispatched / In transit / Delivered)
23. Drivers updating status and sending POD through a Telegram bot
24. A weekly dashboard of best lanes, best brokers, empty-mile % and profit

## Section D: Adoption

25. Would you trust an AI-written email if you could check it before sending? *(Yes / Maybe / No)*
26. Would you let an AI agent phone brokers for you? *(Yes / Only with my approval / No)*: future work
27. What is the most you would pay per month for a tool with these features? *(Free only / up to $25 / $25–75 / $75+)*
28. Anything else a tool like this must do? *(open text)*

---

## Interview guide (3–5 interviews, 15–20 minutes)

Interview experienced dispatchers or fleet owners. Ask permission before recording; take notes otherwise.

1. Walk me through how you found and booked your last load, step by step.
2. Where do things go wrong or take the most time?
3. How do you decide if a rate is good? Show me with a real (anonymised) example.
4. How do you keep track of loads and driver updates today?
5. *(Show Sean AI, or screenshots)* What would you use? What would you never use? Why?
6. What would stop you switching from your current tools?

## Analysing the results (for the report)

- **Need:** % using spreadsheets/chats (Q7, Q8) and ignoring deadhead (Q10) supports the problem statement.
- **Feature priority:** average score for each feature (Q15–Q24) as a bar chart; compare it with what was built.
- **Segments:** compare 1–5 truck carriers with larger fleets (Q2) to support the PID's target group.
- **Willingness to pay:** Q27 against Q13 supports the "low-cost tool" gap.
- **Quotes:** use short anonymised quotes from Q14, Q28 and the interviews.
- Report the number of responses, how participants were found, and the limitations (small,
  self-selected sample), as the PID limitations section says.
