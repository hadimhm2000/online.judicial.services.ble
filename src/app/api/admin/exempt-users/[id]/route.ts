import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;

    const existing = await db.exemptUser.findUnique({
      where: { id },
    });

    if (!existing) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    await db.exemptUser.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'کاربر معاف با موفقیت حذف شد' });
  } catch (error) {
    console.error('Error deleting exempt user:', error);
    return NextResponse.json({ error: 'Failed to delete exempt user' }, { status: 500 });
  }
}
