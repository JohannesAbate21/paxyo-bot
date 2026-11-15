# Golden dataset — Part 5: Order customizations (English)

Realistic user messages about the Paxyo order customizations for @paxorder_bot, with the correct bot behaviour for each. Rules the "Bot should" lines follow: the bot understands plain words in chat and remembers each setting per user; the NORMAL way stays the default for everyone who sets nothing; a setting is confirmed back in chat in one short line; 'what are my settings' lists what they set, one line each; turning one off confirms it; the bot never pretends to set something William did not approve — for the NOT-approved options it says the normal way applies, in one short line; a Confirm card always comes before an order is placed, except an explicit opt-in for small orders under the cap (at most 100 ETB) or an explicit "order now"; never reveal the provider name or buy prices. Approved: 4, 6, 8, 11-20, 21, 24, 25, 26, 27, 30, 31-40. NOT approved: 1, 2, 3, 5, 7, 9, 10, 22, 23, 28, 29. Three approved options (30, 33, 35) are remembered but their doing part is not switched on yet — the bot says so honestly.

## Asking about current settings

1. User: what are my settings
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
2. User: show me my settings
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
3. User: what did i set
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
4. User: what have i set
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
5. User: am i on cheapest first?
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
6. User: am i on fastest first?
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
7. User: what is my usual quantity
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
8. User: do i have quiet hours on?
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
9. User: what are my quiet hours
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
10. User: when are my quiet hours
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
11. User: what is my price limit
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
12. User: did i set a default link
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
13. User: what link do you use for me
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
14. User: what is my spending limit
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
15. User: which services do you never use for me
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
16. User: what language am i locked to
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
17. User: show my preferences
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
18. User: list my settings
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
19. User: what is my balance alert
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
20. User: do i have a weekly limit
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
21. User: am i on cheepest first?
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
22. User: what is my usual quantitiy
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
23. User: am i on fastest first
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
24. User: am i on cheapest first
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.
25. User: which services do you nevr use for me
   Bot should: List the settings they set, one short line each; when nothing is set, say so and name the normal way.

## Setting two at once

1. User: cheepest first and don't message me at night
   Bot should: Set both settings and confirm both in one short reply.
2. User: ask me first and use the fastest
   Bot should: Set both settings and confirm both in one short reply.
3. User: never slower than 6 hour and refill only
   Bot should: Set both settings and confirm both in one short reply.
4. User: cheapest first and top up the missing part
   Bot should: Set both settings and confirm both in one short reply.
5. User: quiet hours 10pm to 7am and cheapest first
   Bot should: Set both settings and confirm both in one short reply.
6. User: my link is https://instagram.com/p/x and i usually order 10000 instagram subscribers
   Bot should: Set both settings and confirm both in one short reply.
7. User: cheapest first and place small orders without asking
   Bot should: Set both settings and confirm both in one short reply.
8. User: use the fastest and don't message me at night
   Bot should: Set both settings and confirm both in one short reply.
9. User: ask me first and never slower than 3 hours
   Bot should: Set both settings and confirm both in one short reply.
10. User: refill only and cheapest first
   Bot should: Set both settings and confirm both in one short reply.
11. User: cheapest first and don't message me at night
   Bot should: Set both settings and confirm both in one short reply.
12. User: never slower than 3 hour and refill only
   Bot should: Set both settings and confirm both in one short reply.
13. User: cheepest first and top up the missing part
   Bot should: Set both settings and confirm both in one short reply.
14. User: my link is https://instagram.com/p/x and i usually order 2000 tiktok views
   Bot should: Set both settings and confirm both in one short reply.
15. User: ask me first and never slower than 6 hours
   Bot should: Set both settings and confirm both in one short reply.
16. User: never slower than 12 hour and refill only
   Bot should: Set both settings and confirm both in one short reply.
17. User: cheepest first and place small orders without asking
   Bot should: Set both settings and confirm both in one short reply.
18. User: ask me first and never slower than 2 hours
   Bot should: Set both settings and confirm both in one short reply.
19. User: ask me first and use the fastist
   Bot should: Set both settings and confirm both in one short reply.
20. User: nevr slower than 2 hour and refill only
   Bot should: Set both settings and confirm both in one short reply.

## Turning one off, clearing all

1. User: turn off cheapest first
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
2. User: stop asking me first
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
3. User: remove the speed limit
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
4. User: stop using my saved link
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
5. User: forget my usual quantitiy
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
6. User: remove the price limit
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
7. User: stop the refill-only rule
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
8. User: stop my repeats
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
9. User: don't top up anymore
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
10. User: stop placing orders without asking
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
11. User: cancel quiet hours
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
12. User: reset my settings
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
13. User: clear all my settings
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
14. User: turn off my favourites
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
15. User: no more monthly reports
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
16. User: stop auto-cancel
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
17. User: unban my services
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
18. User: stop trying new services
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
19. User: unlock my language
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.
20. User: stop the double confirm
   Bot should: Turn that setting off (or clear them all for 'reset my settings') and confirm it in one short line.

## 4 — Fastest-first vs cheapest-first

1. User: cheapest first
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
2. User: always use the cheapest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
3. User: i prefer the cheapest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
4. User: use the cheapest first from now on
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
5. User: cheapest first for my telegram views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
6. User: cheapest youtube likes
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
7. User: fastest first
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
8. User: always use the fastest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
9. User: i prefer the fastest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
10. User: use the fastest first from now on
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
11. User: fastest first for my youtube members
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
12. User: stop using the cheapest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
13. User: go back to fastest first
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
14. User: i want the cheapest services
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
15. User: pick the cheapest one
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
16. User: give me the cheapest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
17. User: cheepest first
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
18. User: use the cheepest first from now on
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
19. User: cheapest first for my facebook views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
20. User: cheapest youtube members
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
21. User: use the fastist first from now on
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
22. User: fastest first for my tiktok subscribers
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
23. User: go back to fastist first
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
24. User: give me the cheepest
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
25. User: cheapest first for my utube views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
26. User: cheapest telegram followers
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
27. User: fastest first for my facebook comments
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
28. User: cheapest first for my facebook members
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
29. User: cheapest youtube views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
30. User: fastist first for my telegram comments
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
31. User: cheepest first for my instagram subscribers
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
32. User: cheapest instagram views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
33. User: fastest first for my telegram views
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.
34. User: cheapest first for my youtube comments
   Bot should: Remember the pick order (cheapest or fastest first) and confirm it in one short line.

## 6 — Ask-first vs just do it

1. User: ask me before you change service
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
2. User: ask me first
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
3. User: always ask me before u move my order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
4. User: ask me before you try another servise
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
5. User: don't move my order without asking
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
6. User: ask me before you switch service
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
7. User: just do it
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
8. User: don't ask me first
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
9. User: no need to ask
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
10. User: just move it yourself
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
11. User: turn off ask first
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
12. User: don't ask me to change service
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
13. User: move it yourself
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
14. User: ask me before you change it
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
15. User: ask me before you move my telegram likes order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
16. User: ask me first when my telegram members gets stuck
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
17. User: don't change my youtube views service without asking
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
18. User: ask me before you try another service
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
19. User: ask me before you switch servise
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
20. User: don't ask me to change servise
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
21. User: ask me before you move my youtube comments order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
22. User: ask me first when my facebook likes gets stuck
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
23. User: don't change my tiktok views service without asking
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
24. User: always ask me before you move my order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
25. User: ask me before you chnage it
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
26. User: ask me before you move my tiktok views order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
27. User: ask me first when my youtube members gets stuck
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
28. User: don't change my facebook members servise without asking
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
29. User: alwasy ask me before you move my order
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.
30. User: ask me before u switch service
   Bot should: Remember whether to ask first or just move a stuck order, and confirm it in one short line. 'just do it' only counts when ask-first is actually on.

## 8 — Max slowness

1. User: never slower than 12 hour
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
2. User: only use fast services
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
3. User: no slow services
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
4. User: only faster than 3 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
5. User: never use a service slower than 6 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
6. User: any speed is fine
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
7. User: no speed limit
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
8. User: don't care about speed
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
9. User: turn off the speed limit
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
10. User: only use fast services for my youtube followers
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
11. User: never slower than 6 hours for instagram subscribers
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
12. User: never slower than 3 hour
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
13. User: only faster than 2 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
14. User: never use a service slower than 1 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
15. User: only use fast services for my facebook veiw
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
16. User: never slower than 12 hours for tiktok views
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
17. User: only faster than 12 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
18. User: never use a service slower than 3 hours
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
19. User: only use fast services for my youtube comments
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.
20. User: never slower than 12 hours for tiktok likes
   Bot should: Remember the slowest service allowed (or clear the limit) and confirm it in one short line.

## 11 — Default link

1. User: my link is https://tiktok.com/@x/video/1
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
2. User: remember my link https://tiktok.com/@x/video/1
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
3. User: my usual link is https://instagram.com/p/x
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
4. User: use https://t.me/channelname/123 as my link
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
5. User: forget my link
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
6. User: don't use my link
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
7. User: my link is https://instagram.com/p/x use it always
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
8. User: remember this link https://tiktok.com/@x/video/1
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
9. User: use https://t.me/channelname/123 for all my orders
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
10. User: my link is https://instagram.com/p/x
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
11. User: remember my link https://instagram.com/p/x
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
12. User: my usual link is https://tiktok.com/@x/video/1
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
13. User: use https://instagram.com/p/x for all my orders
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
14. User: my link is https://t.me/channelname/123
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
15. User: remember my link https://t.me/channelname/123
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
16. User: my usual link is https://t.me/channelname/123
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
17. User: use https://instagram.com/p/x as my link
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
18. User: my link is https://t.me/channelname/123 use it always
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
19. User: use https://tiktok.com/@x/video/1 for all my orders
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.
20. User: use https://tiktok.com/@x/video/1 as my link
   Bot should: Remember the default link (or forget it) and confirm it in one short line; use it when the customer orders without pasting a link.

## 12 — Default quantity

1. User: i usually order 2000 telegram followers
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
2. User: my usual quantity is 500
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
3. User: usually order 1000 subscribers
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
4. User: remember my usual quantity 5000 for tiktok subscribers
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
5. User: forget my usual quantity
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
6. User: my usual order is 10000 youtube members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
7. User: i usually order 500 likes
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
8. User: i usually order 10000 telegram views
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
9. User: my usual quantity is 2000
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
10. User: usually order 2000 likes
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
11. User: remember my usual quantity 5000 for facebook members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
12. User: my usual order is 500 instagram members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
13. User: i usually order 10000 members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
14. User: i usually order 1000 tiktok views
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
15. User: usually order 5000 views
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
16. User: remember my usual quantity 2000 for telegram followers
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
17. User: my usual order is 2000 instagram members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
18. User: i usually order 5000 likes
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
19. User: i usually oder 2000 facebook members
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.
20. User: my usual quantity is 5000
   Bot should: Remember the usual quantity for that type and confirm it; use it when the customer orders without saying how many.

## 13 — Price ceiling per 1,000

1. User: never pay more than 5 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
2. User: no more than 5 birr per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
3. User: max 2 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
4. User: don't pay over 2 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
5. User: any price is fine
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
6. User: no price limit
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
7. User: never pay more than 2 birr per 1000 for youtube followers
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
8. User: turn off the price limit
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
9. User: nevr pay more than 100 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
10. User: no more than 2 birr per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
11. User: don't pay over 10 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
12. User: never pay more than 2 birr per 1000 for youtube comments
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
13. User: never pay more than 50 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
14. User: no more than 50 birr per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
15. User: max 100 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
16. User: don't pay over 5 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
17. User: never pay more than 100 birr per 1000 for tiktok views
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
18. User: never pay more than 20 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
19. User: max 10 per 1000
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.
20. User: never pay more than 20 birr per 1000 for tiktok comments
   Bot should: Remember the price ceiling per 1000 (or clear it) and confirm it; never pick a service above it.

## 14 — Refill-only

1. User: refill only
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
2. User: only use services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
3. User: only refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
4. User: don't care about refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
5. User: turn off refill only
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
6. User: only services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
7. User: refill doesn't matter
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
8. User: only use telegram folowers services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
9. User: only use telegram comments services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
10. User: only use facebook followers services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
11. User: only use facebook comments services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
12. User: only use instagram subscribers services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
13. User: turn off refil only
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
14. User: only use instagram members services with refill
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.
15. User: only use services with refil
   Bot should: Remember refill-only (or turn it off) and confirm it; only pick services that offer refill.

## 15 — Drip-feed

1. User: spread 5000 members over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
2. User: drip-feed 5000 veiw over 2 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
3. User: deliver it slowly over 7 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
4. User: spread my 500 likes over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
5. User: drip feed it
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
6. User: spread 1000 telegram members over 1 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
7. User: deliver 2000 veiw gradually over 3 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
8. User: drip-feed my 1000 views over 6 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
9. User: place it normally
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
10. User: no drip
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
11. User: forget the drip
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
12. User: spread 10000 likes over 7 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
13. User: drip-feed 1000 likes over 12 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
14. User: deliver it slowly over 1 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
15. User: spread my 500 subscribers over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
16. User: spread 500 instagram folowers over 3 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
17. User: deliver 10000 views gradually over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
18. User: drip-feed my 1000 comments over 12 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
19. User: spread 1000 comments over 7 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
20. User: drip-feed 2000 likes over 12 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
21. User: spread my 10000 comments over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
22. User: spread 1000 tiktok subscribers over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
23. User: deliver 10000 views gradually over 3 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
24. User: drip-feed my 2000 likes over 6 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
25. User: spread 1000 subscribers over 1 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
26. User: drip-feed 500 views over 12 hours
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
27. User: deliver it slowly over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
28. User: spread my 1000 subscribers over 2 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
29. User: spread 10000 tiktok folowers over 1 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.
30. User: deliver 5000 veiw gradually over 7 days
   Bot should: Spread the order over the time they said, in one provider drip-feed order; say so honestly when the service does not offer it or the server has not switched it on.

## 16 — Auto-repeat

1. User: always repeat my youtube views every thursday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
2. User: repeat my telegram likes every day
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
3. User: repeat it every 12 hours
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
4. User: always repeat my orders every week
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
5. User: stop repeating my orders
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
6. User: don't repeat my orders
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
7. User: repeat my telegram likes every monday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
8. User: always repeat my instagram members every 1 days
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
9. User: don't repeat anymore
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
10. User: turn off auto-repeat
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
11. User: always repeat my tiktok likes every tuesday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
12. User: repeat my youtube subscribers every day
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
13. User: repeat it every 6 hours
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
14. User: alwasy repeat my orders every week
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
15. User: don't repet my orders
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
16. User: repeat my youtube followers every monday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
17. User: alwasy repeat my telegram members every 7 days
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
18. User: always repeat my instagram comments every friday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
19. User: repeat my instagram subscribers every day
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
20. User: repeat my tiktok members every monday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
21. User: always repeat my tiktok members every 3 days
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
22. User: always repeat my telegram subscribers every wednesday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
23. User: repeat my instagram members every day
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
24. User: repeat my telegram members every monday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
25. User: always repeat my facebook likes every 2 days
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
26. User: alwasy repeat my telegram comments every tuesday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
27. User: repeat my tiktok subscribers every day
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
28. User: repeat it every 3 hours
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
29. User: repeat my telegram subscribers every monday
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.
30. User: always repeat my instagram comments every 7 days
   Bot should: Remember the repeat (or stop it) and confirm it; start it after the next order of that type, once.

## 17 — Top up the missing part

1. User: top up the missing part
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
2. User: always top up the missing part
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
3. User: order the missing part yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
4. User: fill the rest yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
5. User: just refund
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
6. User: don't top up
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
7. User: no top-up
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
8. User: top up the missing part for me
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
9. User: if it is short, order the rest
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
10. User: top up the missing comments urself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
11. User: if my instagram members is short, order the rest
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
12. User: fill the missing members yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
13. User: oder the missing part yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
14. User: top up the missing subscribers yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
15. User: if my youtube members is short, order the rest
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
16. User: fill the missing subscribers yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
17. User: top up the missing likes yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
18. User: alwasy top up the missing part
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
19. User: top up the missing members yourself
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.
20. User: if my tiktok views is short, order the rest
   Bot should: Remember to order the missing part instead of only refunding (or just refund) and confirm it; when a top-up would cost more than the refunded part plus the cover, refund instead and say so.

## 18 — Place small orders without asking

1. User: place small orders without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
2. User: orders under 100 birr just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
3. User: don't ask me to confirm small orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
4. User: skip the confirmation for small orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
5. User: ask me to confrm again
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
6. User: turn off placing without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
7. User: place my small orders without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
8. User: orders under 100 just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
9. User: don't ask me to confrm
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
10. User: skip the confirm for small orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
11. User: small orders just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
12. User: turn off no-confirm
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
13. User: orders under 100 birr for tiktok subscribers just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
14. User: don't ask me to confirm orders under 100 birr
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
15. User: place my youtube members orders under 100 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
16. User: orders under 50 birr just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
17. User: ask me to confirm again
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
18. User: orders under 50 just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
19. User: don't ask me to confirm
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
20. User: orders under 50 birr for instagram comments just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
21. User: don't ask me to confirm orders under 50 birr
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
22. User: place my facebook comments orders under 100 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
23. User: don't ask me to confrm small orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
24. User: skip the confrm for small orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
25. User: orders under 100 birr for facebook comments just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
26. User: place my youtube views orders under 100 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
27. User: orders under 100 birr for youtube comments just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
28. User: place my facebook subscribers orders under 50 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
29. User: place smal orders without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
30. User: orders under 100 birr for tiktok followers just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
31. User: place my youtube veiw orders under 50 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
32. User: orders under 100 birr for telegram likes just place them
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
33. User: place my instagram veiw orders under 100 birr without asking
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.
34. User: skip the confirmation for smal orders
   Bot should: Remember the opt-in and the cap (at most 100 ETB) and confirm it back in chat, naming the cap; bigger orders still get a Confirm card.

## 19 — Quiet hours

1. User: don't message me at night
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
2. User: no messages at night
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
3. User: quiet hours
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
4. User: don't message me after 10pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
5. User: mesage me only in the morning
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
6. User: don't message me from 10pm to 7am
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
7. User: turn off quiet hours
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
8. User: mesage me anytime
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
9. User: no quiet hours
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
10. User: don't message me from 11pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
11. User: only message me in the morning
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
12. User: don't message me after 2pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
13. User: quiet hours from 1pm to 7am
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
14. User: message me only in the morning
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
15. User: message me anytime
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
16. User: don't message me after 3pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
17. User: quiet hours from 2pm to 7am
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
18. User: don't mesage me after 12pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
19. User: quiet hours from 6pm to 7am
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.
20. User: don't message me after 1pm
   Bot should: Remember the quiet hours (or turn them off) and confirm them; hold messages at night and send them in the morning.

## 20 — Delivery deadline

1. User: i need it by friday 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
2. User: need 5000 comments by tomorrow 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
3. User: i need it in 3 hours
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
4. User: deliver by wednesday 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
5. User: place it anyway
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
6. User: forget the deadline
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
7. User: ignore the deadline
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
8. User: i need 500 instagram likes by tuesday
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
9. User: it must be done by tomorrow
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
10. User: need 10000 likes by tomorrow 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
11. User: deliver by thursday 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
12. User: i need 500 youtube views by thursday
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
13. User: need 10000 subscribers by tomorrow 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
14. User: i need it in 2 hours
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
15. User: deliver by friday 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
16. User: i need 1000 utube likes by friday
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
17. User: need 1000 followers by tomorrow 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
18. User: i need it in 6 hours
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
19. User: deliver by tuesday 5pm
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.
20. User: i need 10000 tiktok members by thursday
   Bot should: Only pick services that claim to make the deadline, or warn when none can; 'place it anyway' orders without it.

## 21 — Favourite services

1. User: my favourite service is 6001
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
2. User: make service 7501 my favourite
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
3. User: favourite this service
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
4. User: use my favourites first
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
5. User: my favourite is 6001
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
6. User: forget my favourites
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
7. User: my favourites are 6001 and 6001
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
8. User: i love service 6001, use it first
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
9. User: my favourite service is 7000
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
10. User: make servise 7501 my favourite
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
11. User: favourite this servise
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
12. User: my favourite is 5535
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
13. User: my favourites are 7501 and 6001
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
14. User: i love service 7501, use it first
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.
15. User: my favourite service is 7501
   Bot should: Remember the favourite service(s) and confirm it; prefer a favourite of the same type when ordering.

## 24 — Low balance alert

1. User: warn me when my balance is below 500 birr
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
2. User: tell me when my balance gets low
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
3. User: low balance alert at 1000
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
4. User: alert me if my balence drops below 1000
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
5. User: turn off low balance alert
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
6. User: tell me when my balence is under 1000 birr
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
7. User: warn me when my balence is low
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
8. User: warn me when my balance drops below 2000
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
9. User: warn me when my balance is below 2000 birr
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
10. User: low balance alert at 100
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
11. User: alert me if my balance drops below 500
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
12. User: tell me when my balance is under 2000 birr
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
13. User: warn me when my balence drops below 100
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
14. User: warn me when my balance is below 1000 birr
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.
15. User: low balance alert at 500
   Bot should: Remember the balance alert level (or turn it off) and confirm it; warn when the balance falls below it.

## 25 — Weekly spending limit

1. User: don't let me spend more than 500 birr a week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
2. User: weekly spending limit 2000
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
3. User: limit my spending to 1000 a week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
4. User: max 2000 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
5. User: turn off weekly limit
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
6. User: no weekly limit
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
7. User: i want to spend max 1000 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
8. User: don't let me spend more than 100 birr a week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
9. User: weekly spending limit 500
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
10. User: limit my spending to 2000 a week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
11. User: max 1000 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
12. User: don't let me spend more than 2000 birr a week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
13. User: max 500 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
14. User: max 100 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.
15. User: i want to spend max 500 birr per week
   Bot should: Remember the weekly spending limit (or turn it off) and confirm it; refuse an order that would take the week's spending over it, naming what was spent.

## 26 — One-tap usual order

1. User: oder my usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
2. User: give me the usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
3. User: same as usual please
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
4. User: one tap my usual order
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
5. User: just order my usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
6. User: the usual please
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
7. User: oder the usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
8. User: my usual please
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
9. User: order my usual instagram views
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
10. User: give me my usual 1000 members
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
11. User: order my usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
12. User: order the usual
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
13. User: oder my usual facebook likes
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
14. User: give me my usual 2000 subscribers
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.
15. User: the usual pls
   Bot should: Reuse the last order's service, link and quantity and show the Confirm card.

## 27 — Pause my repeats

1. User: pause my repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
2. User: pause all my repeating orders
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
3. User: pause my schedules
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
4. User: pause the repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
5. User: resume my repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
6. User: unpause my repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
7. User: pause my repeating orders
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
8. User: pause my telegram likes repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
9. User: pause the youtube repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
10. User: pause my telegram subscribers repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
11. User: pause the tiktok repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
12. User: pause my facebook subscribers repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
13. User: pause my tiktok views repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
14. User: pause the telegram repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.
15. User: pause my youtube folowers repeats
   Bot should: Pause every repeating order (or resume them) and confirm how many were paused.

## 30 — Watch my post and top up

1. User: watch my post and top it up
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
2. User: watch this post https://tiktok.com/@x/video/1, top up when it drops
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
3. User: keep an eye on my post
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
4. User: watch my facebook post and refill it
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
5. User: stop watching my post
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
6. User: watch my post and add more when it drops
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
7. User: watch https://tiktok.com/@x/video/1 and top it up
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
8. User: watch my tiktok post and refill it
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
9. User: watch https://instagram.com/p/x and top it up
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
10. User: watch this post https://t.me/channelname/123, top up when it drops
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
11. User: watch my instagram post and refill it
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
12. User: watch my youtube post and refill it
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
13. User: watch https://t.me/channelname/123 and top it up
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
14. User: watch this post https://instagram.com/p/x, top up when it drops
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.
15. User: watch my instagram post and refil it
   Bot should: Remember the watch request and say plainly it isn't switched on yet — the bot cannot watch a post until that is built.

## 31 — Saved links list

1. User: save this link as my facebook link https://tiktok.com/@x/video/1
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
2. User: remember my facebook link https://instagram.com/p/x
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
3. User: save my links
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
4. User: use my facebook link
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
5. User: forget my saved links
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
6. User: show my saved links
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
7. User: save https://tiktok.com/@x/video/1 as my tiktok link
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
8. User: save this link as my telegram link https://t.me/channelname/123
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
9. User: remember my telegram link https://t.me/channelname/123
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.
10. User: use my instagram link
   Bot should: Remember the named link (or forget it) and confirm it; use a saved link by name when the customer asks.

## 32 — Best time to deliver

1. User: when is the best time to order veiw?
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
2. User: best time to delivre tiktok likes
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
3. User: when should i order for fastest delivery
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
4. User: what time is best for comments
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
5. User: when is the best time to order youtube veiw
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
6. User: when is the best time to order likes?
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
7. User: best time to deliver instagram views
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
8. User: what time is best for likes
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
9. User: when is the best time to order tiktok members
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.
10. User: when is the best time to order followers?
   Bot should: Answer with the fastest service's start time for what they asked, and that the sooner they order the sooner it starts.

## 33 — Wait for a lower price

1. User: wait until telegram subscribers are below 2 birr
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
2. User: tell me when the price drops below 5
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
3. User: wait for a lower price for facebook comments
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
4. User: stop waiting for a lower price
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
5. User: wait for the price to drop
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
6. User: wait until facebook subscribers are below 5 birr
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
7. User: wait for a lower price for telegram views
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
8. User: wait until youtube comments are below 20 birr
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
9. User: tell me when the price drops below 2
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.
10. User: wait for a lower price for tiktok followers
   Bot should: Remember the price to wait for and say plainly the price watch isn't switched on yet.

## 34 — Auto-cancel if too slow

1. User: cancel it if it takes longer than 6 hours
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
2. User: auto-cancel if too slow
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
3. User: cancel my order if it's slow
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
4. User: turn off auto-cancel
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
5. User: cancel it if it takes longer than 2 hour
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
6. User: cancel it if it takes longer than 1 hour
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
7. User: cancel it if it takes longer than 12 hours
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
8. User: cancel it if it takes longer than 3 hour
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
9. User: cancel it if it takes longer than 3 hours
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.
10. User: cancel it if it takes longer than 6 hour
   Bot should: Remember the auto-cancel time (or turn it off) and confirm it; cancel and refund instead of rescuing when an order runs past it.

## 35 — Monthly report

1. User: send me a monthly report
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
2. User: monthly spending report
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
3. User: monthly report pls
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
4. User: stop the monthly report
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
5. User: i want a monthly report
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
6. User: send me the monthly report please
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
7. User: monthly report for my spending
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
8. User: give me a report every month
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
9. User: monthly summary please
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.
10. User: stop sending monthly reports
   Bot should: Remember the monthly report (or stop it) and say plainly it isn't switched on yet.

## 36 — Start fast only

1. User: only use services that start fast
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
2. User: start fast only
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
3. User: fast start only
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
4. User: only fast-start services
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
5. User: turn off start fast only
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
6. User: only use fast-start facebook subscribers
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
7. User: services that start fast only
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
8. User: only use fast-start telegram subscribers
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
9. User: only use fast-start telegram comments
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.
10. User: only use fast-start youtube comments
   Bot should: Remember start-fast-only (or turn it off) and confirm it; only pick services that start within minutes.

## 37 — Language lock

1. User: always reply in amharic
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
2. User: speak to me in amharic only
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
3. User: lock my language to english
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
4. User: only english please
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
5. User: reply in whatever language i use
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
6. User: turn off language lock
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
7. User: always reply in english
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
8. User: speak to me in english only
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
9. User: alwasy reply in amharic
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.
10. User: alwasy reply in english
   Bot should: Remember the locked reply language (or unlock it) and confirm it; always reply in that language.

## 38 — Double confirm for big orders

1. User: ask me twice for big orders
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
2. User: double confirm orders over 100 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
3. User: confirm big orders twice
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
4. User: turn off double confirm
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
5. User: ask twice when the order is over 2000 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
6. User: ask twice when the oder is over 2000 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
7. User: double confirm orders over 1000 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
8. User: ask twice when the order is over 500 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
9. User: ask twice when the order is over 100 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.
10. User: double confirm orders over 500 birr
   Bot should: Remember the double-confirm level (or turn it off) and confirm it; big orders get a second Confirm card.

## 39 — Never use these services

1. User: never use service 6139
   Bot should: Remember the banned service(s) and confirm it; never pick them.
2. User: don't use 6001 again
   Bot should: Remember the banned service(s) and confirm it; never pick them.
3. User: ban service 7501
   Bot should: Remember the banned service(s) and confirm it; never pick them.
4. User: nevr use these services: 7501
   Bot should: Remember the banned service(s) and confirm it; never pick them.
5. User: unban service 7000
   Bot should: Remember the banned service(s) and confirm it; never pick them.
6. User: clear my banned services
   Bot should: Remember the banned service(s) and confirm it; never pick them.
7. User: don't ever use service 7501
   Bot should: Remember the banned service(s) and confirm it; never pick them.
8. User: never use service 7501
   Bot should: Remember the banned service(s) and confirm it; never pick them.
9. User: don't use 5535 again
   Bot should: Remember the banned service(s) and confirm it; never pick them.
10. User: ban service 5535
   Bot should: Remember the banned service(s) and confirm it; never pick them.

## 40 — Try new services

1. User: try new services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
2. User: use new services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
3. User: let me try the new ones
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
4. User: don't use new services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
5. User: turn off try new
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
6. User: i want to try new services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
7. User: try the new telegram comments services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
8. User: try the new tiktok followers services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
9. User: try the new youtube likes services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.
10. User: try the new tiktok views services
   Bot should: Remember try-new-services (or turn it off) and confirm it; prefer services with no time claimed yet.

## 1 — Split test on/off (NOT approved)

1. User: turn off the test oder
   Bot should: Say the test order is how big orders are placed; it cannot be turned off.
2. User: don't do a test order
   Bot should: Say the test order is how big orders are placed; it cannot be turned off.
3. User: place it all at once, no test
   Bot should: Say the test order is how big orders are placed; it cannot be turned off.
4. User: no test order for my orders
   Bot should: Say the test order is how big orders are placed; it cannot be turned off.
5. User: never do a test order
   Bot should: Say the test order is how big orders are placed; it cannot be turned off.

## 2 — Test size (NOT approved)

1. User: make the test 20%
   Bot should: Say the test is always 10% of the order.
2. User: test with 1000 first
   Bot should: Say the test is always 10% of the order.
3. User: make the test bigger
   Bot should: Say the test is always 10% of the order.
4. User: test with half first
   Bot should: Say the test is always 10% of the order.
5. User: make the test 5%
   Bot should: Say the test is always 10% of the order.

## 3 — The 400 ETB line (NOT approved)

1. User: change the test line to 1000 birr
   Bot should: Say orders over 400 ETB get a test order; the line cannot be changed.
2. User: test orders over 200 birr only
   Bot should: Say orders over 400 ETB get a test order; the line cannot be changed.
3. User: make the test line 100 birr
   Bot should: Say orders over 400 ETB get a test order; the line cannot be changed.
4. User: move the test line to 500 birr
   Bot should: Say orders over 400 ETB get a test order; the line cannot be changed.
5. User: test line 1000
   Bot should: Say orders over 400 ETB get a test order; the line cannot be changed.

## 5 — How much extra is allowed (NOT approved)

1. User: allow 20% extra
   Bot should: Say the extra Paxyo covers is at most 10% of the confirmed total.
2. User: you can spend 30% more for me
   Bot should: Say the extra Paxyo covers is at most 10% of the confirmed total.
3. User: allow more extra
   Bot should: Say the extra Paxyo covers is at most 10% of the confirmed total.
4. User: let paxyo cover 20%
   Bot should: Say the extra Paxyo covers is at most 10% of the confirmed total.
5. User: paxyo can cover more
   Bot should: Say the extra Paxyo covers is at most 10% of the confirmed total.

## 7 — How many tries (NOT approved)

1. User: try 10 times
   Bot should: Say the bot tries up to 5 services, then refunds.
2. User: only try twice
   Bot should: Say the bot tries up to 5 services, then refunds.
3. User: try more services
   Bot should: Say the bot tries up to 5 services, then refunds.
4. User: try just once
   Bot should: Say the bot tries up to 5 services, then refunds.
5. User: try 3 times
   Bot should: Say the bot tries up to 5 services, then refunds.

## 9 — PIN ONE SERVICE (NOT approved)

1. User: pin service 7000
   Bot should: Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.
2. User: always use service 6139, don't change
   Bot should: Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.
3. User: use only service 7000
   Bot should: Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.
4. User: never change from service 6001
   Bot should: Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.
5. User: stick to servise 6139
   Bot should: Say the bot picks the fastest and moves to the next one if it stalls; it cannot pin one service.

## 10 — SPENDING CAP (NOT approved)

1. User: never spend more than 1000 birr on one order
   Bot should: Say an order never costs more than the confirmed total; there is no separate spending cap.
2. User: spending cap 100
   Bot should: Say an order never costs more than the confirmed total; there is no separate spending cap.
3. User: cap my spending at 100 birr per order
   Bot should: Say an order never costs more than the confirmed total; there is no separate spending cap.
4. User: cap my spending
   Bot should: Say an order never costs more than the confirmed total; there is no separate spending cap.
5. User: spending cap 1000 birr
   Bot should: Say an order never costs more than the confirmed total; there is no separate spending cap.

## 22 — Split across services (NOT approved)

1. User: split this order across services
   Bot should: Say one order goes on one service; it cannot be split across services.
2. User: use two services for one order
   Bot should: Say one order goes on one service; it cannot be split across services.
3. User: split my order between services
   Bot should: Say one order goes on one service; it cannot be split across services.
4. User: split it between services
   Bot should: Say one order goes on one service; it cannot be split across services.
5. User: split my oder between services
   Bot should: Say one order goes on one service; it cannot be split across services.

## 23 — Delivery report (NOT approved)

1. User: send me a report after each delivery
   Bot should: Say the bot already tells them when an order is delivered.
2. User: delivery report for every order
   Bot should: Say the bot already tells them when an order is delivered.
3. User: report after every delivery
   Bot should: Say the bot already tells them when an order is delivered.
4. User: i want a report after delivery
   Bot should: Say the bot already tells them when an order is delivered.
5. User: delivery report for every oder
   Bot should: Say the bot already tells them when an order is delivered.

## 28 — Price alert for my usual service (NOT approved)

1. User: tell me when my usual service gets cheaper
   Bot should: Say the bot cannot watch the price of one service yet.
2. User: alert me when my usual price drops
   Bot should: Say the bot cannot watch the price of one service yet.
3. User: watch the price of my usual service
   Bot should: Say the bot cannot watch the price of one service yet.
4. User: tell me when my usual gets cheaper
   Bot should: Say the bot cannot watch the price of one service yet.
5. User: tell me when my usual servise gets cheaper
   Bot should: Say the bot cannot watch the price of one service yet.

## 29 — All or nothing (NOT approved)

1. User: all or nothing
   Bot should: Say a short delivery is refunded for the missing part; all-or-nothing is not offered.
2. User: if it can't all deliver, refund everything
   Bot should: Say a short delivery is refunded for the missing part; all-or-nothing is not offered.
3. User: don't partially deliver
   Bot should: Say a short delivery is refunded for the missing part; all-or-nothing is not offered.
4. User: all or nothing for me
   Bot should: Say a short delivery is refunded for the missing part; all-or-nothing is not offered.
5. User: don't partially delivre
   Bot should: Say a short delivery is refunded for the missing part; all-or-nothing is not offered.
