# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

I included a Task Class , it included the namem time it would take for an activity, and priority. I included a category object  with different activity options, time of day
An Owner preference for choices and instructions, and a planner class for scheduling
**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

Yes, I it changed a lot. My initial design felt a little messy in some ways. I added things like frequency, and moved certain logic to a different class that made more sense. I wanted to implement a lot more changes, but I was afraid that I would over complicate things and mess it up.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?
it considers avaialbility, priority, and personal owner preferences.

I decided based on practicality. Tasks need to be organized in a way that works better for the pets needs and health. Also considering that most people have many daily tasks, and limited time.
**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?
The scheduler leaves out low- priority tasks when the user/owner has very little free time. The reason that is reasonable, is because feeding and walking for example can not be neglected, specially with bigger dogs.
---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

I used AI to help organize my UML, and refining the python logic. A prompt I used is " If I wanted to help a pet owner organize their pet duties with limited time using a program, what are necessary considerations.

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?
AI suggested a complex schedulor that would have been very time consuming. I mentioned that this scheduler should be simple to fill out, and to the point.
---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

I tested to make sure that the scheduler uses priority correctly, considers preferences for tasks and times, produces an explanation for why it chose the schedule for owner, considers availabilty
**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

I am confident that works, as I tested it a few times myself
---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

I am satisfied with the final product. One of the things that I had trouble with but made sense for me was to add a " start over" button. I am very satisfied that I got it working. 

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

I still believe that this scheduler can be made simpler with less steps, and a more user friendly view. I find the final product to be better but could still improve. The goal is to make it as simple, and less time consuming.

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

I learned that AI is really great at organizing and great with data structure. I was having a hard time with organizing the classes, and thinking of ways to make it easier on the user. I think that less is more when it comes to applications such as this one.
