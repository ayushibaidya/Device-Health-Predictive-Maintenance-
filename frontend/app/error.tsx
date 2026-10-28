"use client";
import { useRouter } from "next/navigation";

export default function ErrorPage({ reset }: { reset: () => void }) {
  const router = useRouter();
  return <div className="card view-state" role="alert"><h1>Unable to display this page</h1>
    <p>Something went wrong while loading device data. Try loading the page again.</p>
    <button className="button" onClick={() => { reset(); router.refresh(); }}>Try again</button></div>;
}
