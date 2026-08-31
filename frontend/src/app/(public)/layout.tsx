import Header from "@/components/Header";

/** 公开页布局：全局导航 + 内容。 */
export default function PublicLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      <Header />
      {children}
    </>
  );
}
