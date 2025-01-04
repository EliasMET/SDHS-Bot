'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Plus, Trash2, Edit2, Save } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { useTheme } from 'next-themes';

interface TryoutGroup {
  group_id: string;
  event_name: string;
  description: string;
  requirements: string[];
  ping_roles: string[];
}

interface TryoutSession {
  session_id: string;
  group_id: string;
  group_name: string;
  channel_id: string;
  voice_channel_id?: string;
  host_id: string;
  lock_timestamp: string;
  requirements: string[];
  description: string;
  voice_invite?: string;
}

export default function TryoutsPage() {
  const { guild } = useParams();
  const { data: session } = useSession();
  const { toast } = useToast();
  const { theme } = useTheme();
  
  const [groups, setGroups] = useState<TryoutGroup[]>([]);
  const [activeSessions, setActiveSessions] = useState<TryoutSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingGroup, setEditingGroup] = useState<TryoutGroup | null>(null);
  const [newGroup, setNewGroup] = useState<Partial<TryoutGroup>>({
    event_name: '',
    description: '',
    requirements: [],
    ping_roles: [],
  });
  const [showNewGroupDialog, setShowNewGroupDialog] = useState(false);
  const [newRequirement, setNewRequirement] = useState('');
  const [newPingRole, setNewPingRole] = useState('');

  useEffect(() => {
    if (session?.access_token && guild) {
      fetchGroups();
      fetchActiveSessions();
    }
  }, [session, guild]);

  const fetchGroups = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/server/${guild}/tryout-groups`, {
        headers: {
          'Authorization': `Bearer ${session?.access_token}`,
        },
      });
      if (!response.ok) throw new Error('Failed to fetch tryout groups');
      const data = await response.json();
      setGroups(data);
    } catch (error) {
      console.error('Error fetching tryout groups:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch tryout groups',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchActiveSessions = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/server/${guild}/active-tryouts`, {
        headers: {
          'Authorization': `Bearer ${session?.access_token}`,
        },
      });
      if (!response.ok) throw new Error('Failed to fetch active sessions');
      const data = await response.json();
      setActiveSessions(data);
    } catch (error) {
      console.error('Error fetching active sessions:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch active tryout sessions',
        variant: 'destructive',
      });
    }
  };

  const handleCreateGroup = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/server/${guild}/tryout-groups`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session?.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newGroup),
      });
      
      if (!response.ok) throw new Error('Failed to create tryout group');
      
      toast({
        title: 'Success',
        description: 'Tryout group created successfully',
      });
      
      setShowNewGroupDialog(false);
      setNewGroup({
        event_name: '',
        description: '',
        requirements: [],
        ping_roles: [],
      });
      fetchGroups();
    } catch (error) {
      console.error('Error creating tryout group:', error);
      toast({
        title: 'Error',
        description: 'Failed to create tryout group',
        variant: 'destructive',
      });
    }
  };

  const handleUpdateGroup = async (group: TryoutGroup) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/server/${guild}/tryout-groups/${group.group_id}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${session?.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(group),
      });
      
      if (!response.ok) throw new Error('Failed to update tryout group');
      
      toast({
        title: 'Success',
        description: 'Tryout group updated successfully',
      });
      
      setEditingGroup(null);
      fetchGroups();
    } catch (error) {
      console.error('Error updating tryout group:', error);
      toast({
        title: 'Error',
        description: 'Failed to update tryout group',
        variant: 'destructive',
      });
    }
  };

  const handleDeleteGroup = async (groupId: string) => {
    if (!confirm('Are you sure you want to delete this tryout group?')) return;
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/server/${guild}/tryout-groups/${groupId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${session?.access_token}`,
        },
      });
      
      if (!response.ok) throw new Error('Failed to delete tryout group');
      
      toast({
        title: 'Success',
        description: 'Tryout group deleted successfully',
      });
      
      fetchGroups();
    } catch (error) {
      console.error('Error deleting tryout group:', error);
      toast({
        title: 'Error',
        description: 'Failed to delete tryout group',
        variant: 'destructive',
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Tryout Settings</h1>
        <Dialog open={showNewGroupDialog} onOpenChange={setShowNewGroupDialog}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="w-4 h-4 mr-2" />
              New Tryout Group
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Tryout Group</DialogTitle>
              <DialogDescription>
                Create a new tryout group for specific events or roles.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="event_name">Event Name</Label>
                <Input
                  id="event_name"
                  value={newGroup.event_name}
                  onChange={(e) => setNewGroup({ ...newGroup, event_name: e.target.value })}
                />
              </div>
              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={newGroup.description}
                  onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                />
              </div>
              <div>
                <Label>Requirements</Label>
                <div className="flex gap-2 mb-2">
                  <Input
                    value={newRequirement}
                    onChange={(e) => setNewRequirement(e.target.value)}
                    placeholder="Add requirement"
                  />
                  <Button
                    onClick={() => {
                      if (newRequirement.trim()) {
                        setNewGroup({
                          ...newGroup,
                          requirements: [...(newGroup.requirements || []), newRequirement.trim()],
                        });
                        setNewRequirement('');
                      }
                    }}
                  >
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {newGroup.requirements?.map((req, index) => (
                    <Badge
                      key={index}
                      variant="secondary"
                      className="flex items-center gap-1"
                    >
                      {req}
                      <button
                        onClick={() => {
                          const newReqs = [...(newGroup.requirements || [])];
                          newReqs.splice(index, 1);
                          setNewGroup({ ...newGroup, requirements: newReqs });
                        }}
                        className="ml-1 hover:text-destructive"
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>
              <div>
                <Label>Ping Roles</Label>
                <div className="flex gap-2 mb-2">
                  <Input
                    value={newPingRole}
                    onChange={(e) => setNewPingRole(e.target.value)}
                    placeholder="Role ID"
                  />
                  <Button
                    onClick={() => {
                      if (newPingRole.trim()) {
                        setNewGroup({
                          ...newGroup,
                          ping_roles: [...(newGroup.ping_roles || []), newPingRole.trim()],
                        });
                        setNewPingRole('');
                      }
                    }}
                  >
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {newGroup.ping_roles?.map((role, index) => (
                    <Badge
                      key={index}
                      variant="secondary"
                      className="flex items-center gap-1"
                    >
                      {role}
                      <button
                        onClick={() => {
                          const newRoles = [...(newGroup.ping_roles || [])];
                          newRoles.splice(index, 1);
                          setNewGroup({ ...newGroup, ping_roles: newRoles });
                        }}
                        className="ml-1 hover:text-destructive"
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowNewGroupDialog(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateGroup}>Create Group</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Separator />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {groups.map((group) => (
          <Card key={group.group_id} className="relative">
            <CardHeader>
              <CardTitle className="flex justify-between items-center">
                {editingGroup?.group_id === group.group_id ? (
                  <Input
                    value={editingGroup.event_name}
                    onChange={(e) =>
                      setEditingGroup({ ...editingGroup, event_name: e.target.value })
                    }
                  />
                ) : (
                  group.event_name
                )}
                <div className="flex gap-2">
                  {editingGroup?.group_id === group.group_id ? (
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => handleUpdateGroup(editingGroup)}
                    >
                      <Save className="w-4 h-4" />
                    </Button>
                  ) : (
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => setEditingGroup(group)}
                    >
                      <Edit2 className="w-4 h-4" />
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => handleDeleteGroup(group.group_id)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {editingGroup?.group_id === group.group_id ? (
                <Textarea
                  value={editingGroup.description}
                  onChange={(e) =>
                    setEditingGroup({ ...editingGroup, description: e.target.value })
                  }
                />
              ) : (
                <p>{group.description}</p>
              )}
              
              <div>
                <h4 className="font-semibold mb-2">Requirements:</h4>
                <ScrollArea className="h-24">
                  <div className="space-y-2">
                    {group.requirements.map((req, index) => (
                      <Badge key={index} variant="secondary">
                        {req}
                      </Badge>
                    ))}
                  </div>
                </ScrollArea>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Ping Roles:</h4>
                <ScrollArea className="h-24">
                  <div className="space-y-2">
                    {group.ping_roles.map((role, index) => (
                      <Badge key={index} variant="outline">
                        {role}
                      </Badge>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {activeSessions.length > 0 && (
        <>
          <Separator />
          <h2 className="text-2xl font-bold mt-8 mb-4">Active Tryout Sessions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {activeSessions.map((session) => (
              <Card key={session.session_id}>
                <CardHeader>
                  <CardTitle>{session.group_name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="mb-2">{session.description}</p>
                  <p className="text-sm text-muted-foreground">
                    Locks at: {new Date(session.lock_timestamp).toLocaleString()}
                  </p>
                  {session.voice_invite && (
                    <Button
                      variant="outline"
                      className="mt-2"
                      onClick={() => window.open(session.voice_invite, '_blank')}
                    >
                      Join Voice Channel
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
} 