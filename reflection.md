# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

I included a Task Class , it included the name, time it would take for an activity, priority. I included a category object  with different activity options, time of day
An Owner preference for choices and instructions, and a planner class for scheduling
**b. Design changes**

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

Yes, I it changed a lot. My initial design lacked organization in some ways. I added things like frequency. And moved certain logic to a different clasds that made more sense.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?
it considers avaialbility, priority, and personal owner preferences.

I decided based on practicality. Tasked need to be organized in a way that works better for the pets safety and health. Also considering that most people have many daily tasks.
**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?
The scheduler leaves out low- priority tasks when the user/owner has very little free time. The reason that is reasonable, is because feeding and walking for example can not be neglected. As it is a major need for a pet.
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

I am satisfied with the final product. I think that this scheduler is actually a brilliant idea.

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

I think adding multiple pets, and a section to include special accomadations for pets

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

I learned that sometimes we have to make a good amount of changes in our designs to better help the user. I learned that AI helps organize classes in a more logical way, really enjoyed seeing that
