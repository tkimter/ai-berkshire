import {getChatGPTUser} from '../../chatgpt-auth';
import {getDb} from '../../../db';
import {readings,submissions} from '../../../db/schema';
import {eq,asc} from 'drizzle-orm';
import curriculum from '../../../lib/curriculum.json';
import {grade,makeProgress} from '../../../lib/grading';
import type {Course,Question,Attempt} from '../../../lib/types';
export const dynamic='force-dynamic';
const course=curriculum as Course;
const json=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
async function state(userId:string){
 const db=getDb();const [r,a]=await Promise.all([db.select().from(readings).where(eq(readings.userId,userId)),db.select().from(submissions).where(eq(submissions.userId,userId)).orderBy(asc(submissions.createdAt),asc(submissions.id))]);
 return makeProgress(r.map(x=>x.conceptId),a.map(x=>({...x,result:JSON.parse(x.resultJson)})) as Attempt[]);
}
export async function GET(){const user=await getChatGPTUser();if(!user)return json({error:'로그인하면 학습 진도를 저장한다.'},401);try{return json(await state(user.userId));}catch{return json({error:'지금은 진도를 읽을 수 없다. 잠시 뒤 다시 시도한다.'},503);}}
export async function POST(req:Request){
 const user=await getChatGPTUser();if(!user)return json({error:'먼저 로그인한다. 학습 기록은 계정에 저장된다.'},401);
 const origin=req.headers.get('origin');if(origin&&origin!==new URL(req.url).origin)return json({error:'요청 출처가 일치하지 않는다.'},403);
 let body:any;try{const text=await req.text();if(text.length>30000)return json({error:'요청이 너무 크다.'},413);body=JSON.parse(text);}catch{return json({error:'요청 형식이 올바르지 않다.'},400);}
 if(!body||typeof body!=='object')return json({error:'요청 형식이 올바르지 않다.'},400);
 try{
  const db=getDb(),userId=user.userId;
  if(body.action==='read'){
   const m=course.modules.find(m=>m.id===body.moduleId);if(!m||!Number.isInteger(body.index)||body.index<0||body.index>=m.concepts.length)return json({error:'없는 개념이다.'},400);
   await db.insert(readings).values({userId,conceptId:`${m.id}:${body.index}`,createdAt:new Date().toISOString()}).onConflictDoNothing();return json({progress:await state(userId)});
  }
  if(body.action!=='submit'||!['module','final','review'].includes(body.kind)||!body.answers||typeof body.answers!=='object'||Array.isArray(body.answers))return json({error:'답안 형식이 올바르지 않다.'},400);
  const current=await state(userId);let questions:Question[]=[];let moduleId:string|null=null;
  if(body.kind==='module'){
   const m=course.modules.find(m=>m.id===body.moduleId);if(!m)return json({error:'없는 장이다.'},400);
   if(!m.concepts.every((_,i)=>current.reads.includes(`${m.id}:${i}`)))return json({error:'이 장의 개념을 모두 마친 뒤 관문에 도전한다.'},403);
   questions=m.questions;moduleId=m.id;
  }else if(body.kind==='final'){
   if(!course.modules.every(m=>(current.best[m.id]??0)>=75))return json({error:'모든 장을 통과해야 수료 시험을 시작할 수 있다.'},403);
   questions=course.finalQuestions;
  }else{
   const id=body.questionId;if(typeof id!=='string'||!current.wrong.some(q=>q.id===id))return json({error:'이 문제는 이미 복습 목록에 없다.'},400);
   questions=[...course.modules.flatMap(m=>m.questions),...course.finalQuestions].filter(q=>q.id===id);
  }
  if(questions.some(q=>body.answers[q.id]===undefined||String(body.answers[q.id]).trim()===''))return json({error:'모든 문제에 답한 뒤 제출한다.'},400);
  const result=grade(questions,body.answers,body.kind);
  await db.insert(submissions).values({id:crypto.randomUUID(),userId,kind:body.kind,moduleId,score:result.score,passed:result.passed,resultJson:JSON.stringify(result),createdAt:new Date().toISOString()});
  return json({result,progress:await state(userId)});
 }catch{return json({error:'저장하지 못했다. 답은 현재 페이지에 남아 있다. 다시 시도한다.'},503);}
}
